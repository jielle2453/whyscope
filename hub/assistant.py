"""Parent assistant: the UGen300 as the parent's helper.

1. A question the device could not answer (abstained, not sensitive, not gibberish) becomes a "to answer" item for the
   parent (table `todo`). The same question asked again by the child only raises the item's count.
2. While no child request is running and none has arrived for `assistant.idle_s` (default 20 s), a background thread
   takes the open items one by one and asks the worker LLM for a DRAFT: at most 3 short sentences for the child plus one
   "Try it together" activity, grounded in the facts of the 3 best-matching principles / entries (the context used is
   stored with the draft and shown to the parent). The draft is written ONE SENTENCE PER CALL, so the worker is free
   again after a few seconds and a child request (which waits on the same GenAI lock) is never stuck behind a whole
   draft: the thread checks for a waiting child between sentences, stops, keeps what it has, and resumes later.
3. hub/wording.py checks the draft; failures are marked, never hidden. A draft is NEVER sent to a child: only the
   parent's Approve / Edit turns it into a family answer (hub/family.py) and queues a delivery for the kid page.
Only the hailo backend drafts (the LLM is the worker's); other modes still list the items so the parent can type an answer.
"""
import json
import re
import threading
import time

import numpy as np

from . import compose, wording
from .db import now
from .recall import content_en, normalize, normalize_en, plausible

SHOTS = 3   # sentences before the activity
NL = "\n"


class _Preempted(Exception):
    """The worker stopped a low-priority draft sentence because a child request was waiting."""

SYSTEM = {
    "en": ("You help a parent answer a child aged 5 to 8 who asked a \"why\" question. Write what the parent can say. Rules:\n"
           "1. Use only the facts given. Do not add new facts. If the facts do not really answer the question, say what we do know, "
           "then say we can find out together.\n"
           "2. Write exactly 3 short sentences, each with at most 12 words, in words a 6-year-old knows. No science words.\n"
           "3. Then write one line that starts with \"Try it together:\" and one simple thing to do at home with everyday things.\n"
           "4. Never praise the child. Never say \"I think\" or \"I like\"."),
    "zh": ("你在幫爸爸媽媽回答5到8歲孩子的「為什麼」問題，寫出爸媽可以說的話。規則：\n"
           "1. 只能用「事實」裡的資訊，不可以加入新知識。如果事實沒有真的回答問題，就說我們知道的，再說我們一起去查查看。\n"
           "2. 寫3句短句，每句最多18個字，用小朋友聽得懂的話，不用科學名詞。\n"
           "3. 然後另起一行，以「試試看：」開頭，寫一個在家用日常東西就能做的小活動。\n"
           "4. 不誇獎孩子，不說「我覺得」「我喜歡」。用台灣繁體中文。")}
# two worked examples: one with facts that answer the question, one with no facts found (the model then says so)
SHOT = {
    "en": [("Question: Why does my spoon look bent in a glass of water?\nFacts:\n- Light bends when it goes from water into air.\n"
            "- That is why a straw in a glass of water looks bent.\nWrite the answer for the child.",
            "Light bends when it goes from water into air. That is why the spoon looks bent. The spoon is still straight.\n"
            "Try it together: Put a straw in a glass of water and look from the side."),
           ("Question: Why do frogs have long tongues?\nFacts:\n- (none found)\nWrite the answer for the child.",
            "I do not know that yet. We can find out together. A book about frogs may tell us.\n"
            "Try it together: Look at pictures of frogs and draw your favorite one.")],
    "zh": [("問題：為什麼湯匙放進水杯看起來是彎的？\n事實：\n- 光從水裡走到空氣裡會拐彎。\n- 所以水杯裡的吸管看起來是彎的。\n請寫給孩子聽的答案。",
            "光從水裡走到空氣裡會拐彎。所以湯匙看起來是彎的。湯匙其實是直的。\n試試看：把吸管放進水杯，從旁邊看一看。"),
           ("問題：為什麼青蛙的舌頭很長？\n事實：\n- （沒有找到）\n請寫給孩子聽的答案。",
            "這個我還不知道。我們一起去查查看。看看青蛙的書，也許會知道。\n試試看：找青蛙的照片，畫出你最喜歡的那一張。")]}
LABEL = {"en": "Try it together:", "zh": "試試看："}
ENDS = {"en": ".!?", "zh": "。！？"}
_SENT_END = {"en": re.compile(r"[.!?]"), "zh": re.compile(r"[。！？]")}


def user_msg(lang: str, question: str, facts: list) -> str:
    fl = "\n".join(f"- {f}" for f in facts) or ("- （沒有找到）" if lang == "zh" else "- (none found)")
    if lang == "zh":
        return f"問題：{question}\n事實：\n{fl}\n請寫給孩子聽的答案。"
    return f"Question: {question}\nFacts:\n{fl}\nWrite the answer for the child."


def split_draft(text: str, lang: str):
    """(sentences before the activity, activity text with its label or None)."""
    label_at = text.find(LABEL[lang].rstrip(":：")) if text else -1
    head, act = (text[:label_at], text[label_at:].strip()) if label_at >= 0 else (text or "", None)
    sents = [s.strip() for s in re.findall(r"[^.!?。！？\n]+[.!?。！？]?", head) if s.strip()]
    return sents, act


_WH_EN = re.compile(r"^\s*(?:why|how|what|where|when|who|which|can|do|does|did|is|are|was|will|could)\b", re.I)


def worth_asking(q: str, lang: str) -> bool:
    """Is this a real question a parent could answer (not gibberish, not a statement)? The knowledge base's own
    plausibility check is too strict here: a question about zebras is fine even though no entry mentions zebras."""
    if lang != "en":
        return plausible(q)
    toks = normalize_en(q).split()
    return (len(toks) >= 3 and len(set(toks)) >= 3 and any(len(t) >= 3 for t in toks)
            and bool(_WH_EN.search(q) or q.rstrip().endswith("?")))


class ParentAssistant:
    def __init__(self, pipe):
        self.p = pipe
        c = pipe.cfg.get("assistant") or {}
        self.enabled = bool(c.get("enabled", True))
        self.idle_s = float(c.get("idle_s", 20))
        self.poll_s = float(c.get("poll_s", 2))
        self.max_new = int(c.get("max_new", 40))       # tokens per sentence call
        self.ctx_floor = float(c.get("context_floor", 0.6))   # a retrieved principle / entry below this is shown but not given to the model
        self._cl = threading.Lock()
        self._inflight = 0
        self._last_child = time.monotonic()
        self.current = None        # todo id being drafted right now
        self.history = []          # [{id, ms, calls, source_ids, ok}] of finished drafts (last 50)
        self.error = None
        self.paused_for_child = 0  # how many times a draft stopped for a child request (for the log)
        self.preempted = 0         # ... of those, stopped mid-sentence by the worker (priority "low")
        if self.enabled:
            threading.Thread(target=self._run, daemon=True, name="parent-assistant").start()

    # ------------------------------------------------------------ child priority
    def child_begin(self):
        with self._cl:
            self._inflight += 1
            self._last_child = time.monotonic()

    def child_end(self):
        with self._cl:
            self._inflight = max(0, self._inflight - 1)
            self._last_child = time.monotonic()

    def child_busy(self) -> bool:
        return self._inflight > 0

    def idle_for(self) -> float:
        return time.monotonic() - self._last_child

    def llm_ready(self) -> bool:
        cp = self.p.composer
        return bool(cp.ready and cp.backend == "hailo" and getattr(cp, "llm", None) is not None)

    # ------------------------------------------------------------ items
    def note_question(self, event_id, question: str, lang: str):
        """Create (or count) a to-answer item for an abstained question; None if it is not worth the parent's time."""
        q = (question or "").strip()
        if not q:
            return None
        if not worth_asking(q, lang):
            return None
        norm = normalize_en(q) if lang == "en" else normalize(q)
        ev = self.p.db.get_event(event_id) if event_id else None
        return self.p.db.todo_add(event_id, q, norm, lang, (ev or {}).get("child_id"))   # the item belongs to the child who asked

    def view(self, it: dict) -> dict:
        """An item as the parent page needs it."""
        def js(v, d):
            try:
                return json.loads(v) if v else d
            except Exception:
                return d
        return {"id": it["id"], "child_id": it.get("child_id"), "event_id": it["event_id"], "question": it["question"], "lang": it["lang"], "count": it["count"],
                "status": it["status"], "ts": it["ts"], "last_ts": it["last_ts"],
                "draft": it["draft"] or "", "partial": it["partial_draft"] or "", "context": js(it["context"], []),
                "wording": js(it["wording"], None), "draft_ms": it["draft_ms"] or 0, "drafted_ts": it["drafted_ts"],
                "origin": it.get("origin") or "abstain",   # "ai_guess": the child already heard this draft
                "drafting": self.current == it["id"], "weak": bool(js(it["context"], [])) and not any(c.get("used", True) for c in js(it["context"], [])), "can_draft": self.enabled and self.llm_ready()}

    def items(self, child_id=None) -> list:
        """Open items of one child (None = every child)."""
        return [self.view(i) for i in self.p.db.todo_list(child_id=child_id)]

    def approve(self, item_id: int, answer=None) -> dict:
        db = self.p.db
        it = db.todo_get(item_id)
        if not it or it["status"] not in db.TODO_OPEN:
            raise KeyError("no open item")
        text = (answer if answer is not None else it["draft"] or "").strip()
        if not text:
            raise ValueError("answer is empty")
        if len(text) > 800:
            raise ValueError("answer is too long")
        hh = db.child_household(it.get("child_id")) or 1   # a family answer belongs to the household, the delivery to the child
        with self.p.lock:
            fid = self.p.family.add(it["question"], it["lang"], text, it["event_id"], it["id"], hh)
        db.todo_update(item_id, status="approved", final=text, resolved_ts=now(), family_id=fid)
        # an AI guess the child already heard and the parent approved unchanged: kept as a family answer, not told again
        same = it.get("origin") == "ai_guess" and text == (it.get("draft") or "").strip()
        did = None if same else db.delivery_add(fid, it["question"], text, it["lang"], it.get("child_id"))
        if it["event_id"]:
            db.mark_talked(it["event_id"])
        return {"ok": True, "family_id": fid, "delivery_id": did, "wording": self.check(text, it["lang"], None)}

    def dismiss(self, item_id: int) -> dict:
        db = self.p.db
        it = db.todo_get(item_id)
        if not it or it["status"] not in db.TODO_OPEN:
            raise KeyError("no open item")
        db.todo_update(item_id, status="dismissed", resolved_ts=now())
        if it["event_id"]:
            db.mark_talked(it["event_id"])
        return {"ok": True}

    def redraft(self, item_id: int) -> dict:
        db = self.p.db
        it = db.todo_get(item_id)
        if not it or it["status"] not in db.TODO_OPEN or self.current == item_id:
            raise KeyError("no open item to redraft")
        db.todo_update(item_id, status="pending", draft="", partial_draft="", wording=None, draft_ms=0, origin="abstain")
        return {"ok": True}

    def status(self, child_id=None) -> dict:
        return {"enabled": self.enabled, "llm_ready": self.llm_ready(), "idle_s": self.idle_s, "idle_for": round(self.idle_for(), 1),
                "child_busy": self.child_busy(), "drafting": self.current, "open": len(self.p.db.todo_list(child_id=child_id)),
                "paused_for_child": self.paused_for_child, "preempted": self.preempted, "error": self.error,
                "last": self.history[-1] if self.history else None}

    # ------------------------------------------------------------ context
    def context_for(self, question: str, lang: str, k: int = 3) -> list:
        """The k best-matching principles / entries with the facts that best fit the question:
        [{kind, id, name, score, facts}]."""
        p = self.p
        with p.lock:
            cands = []
            if p.principles.enabled:
                for pr, sc in p.principles.top(question, lang, k):
                    cands.append(("principle", pr["id"], pr.get(f"name_{lang}") or pr.get("name_en"), sc,
                                  list(pr.get(f"facts_{lang}") or pr.get("facts_en") or [])))
            raw = p.recall.raw_scores(question, lang)
            for i in np.argsort(-raw)[:k]:
                e = p.recall.entries[int(i)]
                f = p.recall.fields(e, lang)
                if raw[i] > 0 and f.get("facts"):
                    cands.append(("entry", e["id"], (f.get("labels") or [e["id"]])[0], float(raw[i]), list(f["facts"])))
            top = sorted(cands, key=lambda c: -c[3])[:k]
            qv = p.recall._embed([normalize_en(question) if lang == "en" else normalize(question)])[0]
            out = []
            for kind, cid, name, sc, facts in top:
                fv = p.recall._embed([normalize_en(f) if lang == "en" else normalize(f) for f in facts])
                keep = sorted(np.argsort(-(fv @ qv))[:2])    # the 2 most relevant facts, in their own order
                out.append({"kind": kind, "id": cid, "name": name, "score": round(sc, 3), "used": sc >= self.ctx_floor,
                            "facts": [facts[int(j)] for j in keep]})
        return out

    # ------------------------------------------------------------ drafting
    def check(self, text: str, lang: str, facts: list) -> dict:
        """hub/wording.py checks on the whole draft (3 sentences + the activity), plus a soft grounding flag."""
        sents, act = split_draft(text, lang)
        probs = []
        body = " ".join(sents) if lang == "en" else "".join(sents)
        if lang == "en":
            probs += wording.check_text_en(body, SHOTS) if body else ["empty"]
            if act:
                probs += wording.check_text_en(act.split(":", 1)[-1].strip(), 1)
            else:
                probs.append("no activity")
        else:
            probs += wording.check_text(body, SHOTS) if body else ["empty"]
            if act:
                probs += wording.check_text(act.split("：", 1)[-1].strip(), 1)
            else:
                probs.append("no activity")
        loose = []
        if sents and facts is not None:   # sentences that bring words the facts do not have (the model may have added something)
            src = " ".join(facts)
            if lang == "en":
                loose = [s for s in sents if not compose.novelty_ok_en(s, src, 1)]
            else:
                loose = [s for s in sents if not compose.novelty_ok(s, src, compose.NOVELTY_MIN)]
        return {"ok": not probs, "problems": probs, "not_in_facts": loose}

    def _one(self, lang: str, question: str, facts: list, partial: str, activity_step: bool) -> str:
        """One LLM call on the worker: the next sentence (or the activity line) after `partial`."""
        from .hailo import chatml
        sysm = {"role": "system", "content": SYSTEM[lang]}
        shots = [m for u, a in SHOT[lang] for m in ({"role": "user", "content": u}, {"role": "assistant", "content": a})]
        prefix = chatml([sysm] + shots)
        head = partial.rstrip()
        if activity_step:
            head = head + ("\n" if head else "") + LABEL[lang]
        turn = chatml([{"role": "user", "content": user_msg(lang, question, facts)}]) + "<|im_start|>assistant\n" + head
        llm = self.p.composer.llm
        if hasattr(llm, "complete_ex"):   # low priority: the worker stops this sentence when a child request arrives
            r = llm.complete_ex(prefix, turn, self.max_new, {"ends": ENDS[lang], "n": 1}, "low")
            if r.get("preempted"):
                raise _Preempted()
            out = r["text"]
        else:
            out = llm.complete(prefix, turn, self.max_new, {"ends": ENDS[lang], "n": 1})
        out = out.replace("<|im_end|>", "").strip()
        if activity_step:
            return (LABEL[lang] + (" " if lang == "en" else "") + out).strip()
        return out

    def draft(self, it: dict) -> bool:
        """Draft one item, one sentence per worker call, stopping (and keeping the text so far) when a child needs the
        worker. Returns True when the draft is finished."""
        db, lang, q = self.p.db, it["lang"], it["question"]
        end = "." if lang == "en" else "。"
        sep = " " if lang == "en" else ""
        self.current = it["id"]
        db.todo_update(it["id"], status="drafting")
        try:
            ctx = json.loads(it["context"]) if it["context"] else None
            if not ctx:
                ctx = self.context_for(q, lang)
                db.todo_update(it["id"], context=json.dumps(ctx, ensure_ascii=False))
            facts = [f for c in ctx if c.get("used", True) for f in c["facts"]]
            partial, ms, calls = it["partial_draft"] or "", int(it["draft_ms"] or 0), 0
            skip_to_activity = False
            while True:
                if self.child_busy() or not self.enabled:   # a child request has priority on the worker
                    db.todo_update(it["id"], status="pending", partial_draft=partial, draft_ms=ms)
                    self.paused_for_child += 1
                    return False
                sents, act = split_draft(partial, lang)
                if act and _SENT_END[lang].search(act.split(LABEL[lang][-1], 1)[-1]):
                    break
                activity_step = bool(act) or skip_to_activity or len(sents) >= SHOTS
                t = time.perf_counter()
                try:
                    piece = self._one(lang, q, facts, sep.join(sents), activity_step)
                except _Preempted:   # a child request took the device mid-sentence: drop that sentence, resume later
                    db.todo_update(it["id"], status="pending", partial_draft=partial, draft_ms=ms)
                    self.paused_for_child += 1
                    self.preempted += 1
                    return False
                ms += int((time.perf_counter() - t) * 1000)
                calls += 1
                body = piece.strip()
                if activity_step:
                    if not _SENT_END[lang].search(body):
                        body += end
                    partial = sep.join(sents) + NL + body
                elif body.startswith(LABEL[lang].rstrip(":：")):   # the model went to the activity by itself
                    if not _SENT_END[lang].search(body):
                        body += end
                    partial = sep.join(sents) + NL + body
                elif not body.strip(" ." + end):                      # nothing more to say: on to the activity
                    if not sents:
                        raise RuntimeError("the model wrote nothing")
                    skip_to_activity = True
                else:
                    if not _SENT_END[lang].search(body):
                        body += end
                    partial = sep.join(sents + [body])
                db.todo_update(it["id"], partial_draft=partial, draft_ms=ms)
            text = partial.strip()
            cur = db.todo_get(it["id"])
            if not cur or cur["status"] not in ("drafting", "pending"):   # approved / dismissed meanwhile: leave it alone
                return True
            w = self.check(text, lang, facts)
            db.todo_update(it["id"], status="ready", draft=text, partial_draft="", wording=json.dumps(w, ensure_ascii=False),
                           draft_ms=ms, drafted_ts=now())
            self.history = (self.history + [{"id": it["id"], "ms": ms, "calls": calls, "ok": w["ok"],
                                             "context": [c["id"] for c in ctx]}])[-50:]
            return True
        except Exception as e:   # the worker went away, a timeout ...: try this item again later
            self.error = f"{type(e).__name__}: {str(e)[:160]}"
            db.todo_update(it["id"], status="pending")
            time.sleep(10)
            return False
        finally:
            self.current = None

    def _run(self):
        while True:
            time.sleep(self.poll_s)
            try:
                if not (self.enabled and self.llm_ready()) or self.child_busy() or self.idle_for() < self.idle_s:
                    continue
                it = self.p.db.todo_next()
                if it:
                    self.draft(it)
            except Exception as e:
                self.error = f"{type(e).__name__}: {str(e)[:160]}"
                time.sleep(5)
