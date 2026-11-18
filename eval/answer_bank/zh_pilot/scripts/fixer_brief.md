# Fixer brief: apply the independent review to the zh pilot

Rules for the fields are in writer_brief.md (same folder); read it first. Then apply this review policy:

1. Fix EVERY `must` issue. Use the reviewer's suggestion when it is good; otherwise write a better fix. If you
   disagree with a must issue, keep the text and say why in `fix_note` (counts as "rejected").
2. Germs policy (team-wide): say 細菌 (not 小蟲蟲 / 很小很小的小蟲蟲 / 髒東西) wherever the English means germs or
   bacteria, in all fields. For viruses keep plain wording you judge natural (e.g. 讓人生病的細菌和病毒 is fine only if
   the English says both). The validator reports 細菌 as a warning (a proposed hub exception); that is expected.
3. Also apply these nits:
   - ask-backs that just re-ask what a1/a2 already said (a memory check, not a guess): rewrite into a real guess about
     the object (still faithful: don't invite a guess whose answer is unsupported or false);
   - variants that ask a different question than the item (query nits): replace with a same-meaning variant;
   - any variant using 蛋蛋 (Taiwanese slang for testicles): replace;
   - tw_note suggestions: add the note when the reviewer is right (keep the form "not_for_tw: …" / "adapted: …");
   - a1_zh_mix flagged as forced: set to null.
   Other nits: apply when clearly better and cheap; otherwise leave.
4. Keep every hard rule (a1_zh one sentence <=18 spoken chars, a2 1-2 sentences <=18 each, ask-back rules, 4-6
   variants with one mixed, a1_zh_mix null or exactly one English word that is also in key_en, key_en 0-2).

Output: a JSONL with ONLY the rows you changed (full row, all fields, same schema as the input pilot rows) plus two extra
keys: `"fix_note"`: short English list of what changed and why, `"fixed_issues"`: number of reviewer issues addressed.
Run the validator on your output (command in writer_brief.md) until 0 rows have errors.
