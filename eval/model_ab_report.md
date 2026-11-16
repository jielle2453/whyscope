# LLM A/B on the UGen300: Qwen2.5-1.5B vs Qwen3-1.7B vs Qwen3-VL-2B (2026-11-16)

**All quality labels on this page are AI-judged** (one strict AI judge, no human review yet). Latency is measured on the
ASUS UGen300 USB (Hailo-10H, HailoRT 5.3.2) at 1.5 A USB power, end to end through the hub (`eval/run_chat.py`).

## Setup

* Question set: `eval/guess_fresh_en.jsonl`, 65 new English questions (body 10, animals 10, nature 11, space 9, home 11,
  society 12, plus the user's 2 real questions). None of them was used to tune prompts. Overlap was checked against the 2786
  questions of the existing sets and KB question patterns (MiniLM cosine below 0.78; obvious paraphrases removed).
* Chat set: `eval/chat_set_en.jsonl` (50 turns, unchanged).
* Each model was the only GenAI model on the worker (the device holds one, see `docs/ugen.md`), with the same hub code,
  prompts and guard, `chat.guess_timeout_s` / `timeout_s` raised to 13 s so slow models were not cut by the timeout.
  Qwen3 runs with thinking off (an empty `<think></think>` block is put after the assistant tag; think blocks are stripped).
* Verdicts for AI guesses: **R** right, **P** partly right, **W** weak (vague, no false fact), **F** contains a false
  statement. Chat replies: appropriate / weak / inappropriate.

## Results

AI guesses on the fresh set (questions that nothing curated covers; the rest abstained or went to chat):

| model | guesses | R / P / W / F | false share | guess reply median / p90 | abstain reply median |
|---|---|---|---|---|---|
| **Qwen2.5-1.5B (kept)** | 41 | 11 / 12 / 10 / **8** | **19.5 %** | **4.9 / 5.4 s** | 5.8 s (19 abstained) |
| Qwen3-1.7B | 42 | 11 / 8 / 8 / 15 | 36 % | 8.8 / 9.8 s | 9.8 s (18) |
| Qwen3-VL-2B (as text model) | 46 | 13 / 13 / 7 / 13 | 28 % | 7.8 / 9.0 s | 8.8 s (14) |

Chat set (50 turns):

| model | appropriate / weak / inappropriate | model replies used | LLM chat reply median / p90 | KB answer full reply median |
|---|---|---|---|---|
| **Qwen2.5-1.5B** | 45 / 5 / 0 | 22 | 4.4 / 6.5 s | 4.3 s |
| Qwen3-1.7B | 47 / 3 / 0 | 6 (25 empty model outputs became canned lines) | 9.5 / 10.7 s | 7.4 s |
| Qwen3-VL-2B | 42 / 7 / 1 | 26 | 8.9 / 10.1 s | 7.4 s |

Qwen3's chat score is high only because its empty outputs were replaced by safe canned lines. Qwen3-VL's inappropriate reply:
c05 "Do you know what is this?" with no picture given to the model, it said "I see a doll!".

Re-run with the kept configuration after the code changes (production config, 2026-11-16): chat set 50/50 replies, LLM
reply median 4.5 s, p90 6.4 s.

## Decision

Rule set before the run: take the model with the fewest false statements whose full reply stays under about 6 s, otherwise
keep Qwen2.5. **Qwen2.5-1.5B is kept**: it has the lowest false share (8/41) and is the only one under 6 s. Qwen3-1.7B is
slower (3.8 vs 5.7 tokens/s; its 147 MB prompt contexts take about 3 s to restore over USB against 0.8 s), states more false
facts and often ends its turn at once (6 empty guesses, 25 empty chat replies). Qwen3-VL-2B is better than Qwen3 on facts but
still worse than Qwen2.5 and about 3 s slower per reply; it is only worth it for the camera (see `docs/ugen.md`
"Eyes, part 2: the VLM", which also has the VLM-vs-CLIP calibration).

The user's two real questions:

* "Why my hair is black? I want a blonded hair": Qwen2.5 **R** ("... a special kind of hair stuff that makes it look dark"),
  Qwen3 **F** ("special kind of green stuff"), Qwen3-VL **F**.
* "why i need to go to bed at 10": a rule question, all three go to the chat path; Qwen2.5 answers "Grown-ups make rules to help
  you grow strong and safe. Why don't we ask them about it?".

## Files

* Raw replies: `eval/chat_results/ab_{q25,q3,vl}_{fresh,chat}.jsonl`; verdicts: `eval/chat_results/ab_judgments.json`.
* Reproduce: start the worker with one model (`hailo.llm_hef`, or `hailo.vlm_hef` with an empty `llm_hef`), then
  `python eval/run_chat.py eval/guess_fresh_en.jsonl --out ...` (run it against a hub on a copy of the database).

## Per question (AI guesses; "(abstain)" = the hub said it would ask a grown-up, "(chat)" = chat path)

| id | question | Qwen2.5-1.5B | Qwen3-1.7B | Qwen3-VL-2B |
|---|---|---|---|---|
| f-001 | Why does my foot fall asleep? | **P** I think your foot falls asleep because it's not moving for a long time. | **F** I think your foot might fall asleep because it's warm and wet, like after a long time in water. | **F** Maybe your foot falls asleep when you walk on it and it gets warm. |
| f-002 | Why do my cheeks get red when I'm shy? | **W** I think when you're feeling shy, your body gets a bit hot. | **P** I think your cheeks get red when you're shy because you're feeling nervous or happy. | (abstain) |
| f-003 | Why do I have knees? | (abstain) | **R** I think knees help you walk and run, like a little bridge for your body. | **F** Maybe your knees are from when you walked or ran a lot, and your body got tired. |
| f-004 | Why do my lips get dry in winter? | **R** I think your lips get dry in winter because it's cold outside, and the air is very dry. | **W** I think your lips get dry in winter because your body loses water when you breathe and sweat. | (abstain) |
| f-005 | Why does my nose run when I eat spicy food? | (abstain) | **F** I think your nose runs because tiny hairs in your nose catch the spice from food. | **F** Maybe your nose runs when you eat spicy food because the tiny hairs in your nose catch the spicy smell. |
| f-006 | Why do I get a cramp in my leg? | (abstain) | (abstain) | (abstain) |
| f-007 | Why do I have hair on my arms? | **F** I think your hair on your arms is like a little brush that keeps you dry when it's wet. | **F** I think hair on your arms might be from the wind or the sun. | (abstain) |
| f-008 | Why does my mouth water when I see candy? | **W** I think your mouth waters when you see candy because the sweet smell makes it feel like a tasty treat. | **W** I think it's because candy is sweet and makes your mouth feel happy. | **W** Maybe the candy makes your mouth feel warm and sweet, so it gets a little wet. |
| f-009 | Why can't I tickle myself? | (abstain) | **F** I think you can't tickle yourself because your nose doesn't have a big part to tickle. | **F** Maybe you can't tickle yourself because you're too small, and your nose is too big. |
| f-010 | Why do I talk in my sleep? | **W** I think when you sleep, your body gets tired from using all the strength. | (abstain) | **W** Maybe your body is tired from using strength, so it talks in your sleep. |
| f-011 | Why do cows chew all day? | (abstain) | **P** I think cows chew all day to help them eat the grass and make their milk. | (abstain) |
| f-012 | Why do crabs walk sideways? | **F** I think crabs walk sideways because they have to use their claws and pincers as legs. | **F** I think crabs walk sideways because they don't have arms like other animals. | **P** Maybe crabs walk sideways to move faster across the sand. |
| f-013 | Why do parrots copy what we say? | **W** I think parrot's brains are like a computer, and they can copy what we say. | (abstain) | **R** Maybe parrots learn to copy sounds and words from their parents or other birds. |
| f-014 | Why do ducks walk in a line? | **P** I think some ducks like to walk in a line because it's safer for them. | **F** I think ducks walk in a line to stay together and keep warm. | **P** Maybe ducks walk in a line to stay safe and not get caught in the water. |
| f-015 | Why do hamsters stuff their cheeks? | **R** I think hamsters stuff their cheeks to keep food in for when they go back into their burrows. | (abstain) | **W** Maybe hamster cheeks are full of food, so they stuff it in a little pouch. |
| f-016 | Why do goats climb rocks? | (abstain) | **P** I think goats climb rocks to find food and to see if there's a good place to eat. | **P** Maybe goats go up rocks to find food or to rest. |
| f-017 | Why do ladybugs have spots? | **F** I think lady bugs have spots to help them see better in the dark. | **F** I think ladybugs have spots because they use them to hide from bad weather. | **F** I think ladybug spots help them hide from bad weather. |
| f-018 | Why do dogs pant? | **R** I think dogs pant because they have to cool off. | **R** I think dogs pant to cool down when they are hot. | **R** Maybe dogs pant when they get hot or tired, like when they run or play. |
| f-019 | Why do cats bring dead mice home? | (abstain) | (abstain) | (abstain) |
| f-020 | Why do hippos stay in the water? | **F** I think hippos stay in the water because they need to swim and live their whole lives there. | **F** I think hippos stay in the water because they need to breathe and stay safe in the water. | **F** Maybe hippos stay in the water to keep their skin dry and stay safe from the sun. |
| f-021 | Why are pine cones closed when it rains? | (abstain) | **R** I think pine cones close when it rains to keep the seeds safe and dry. | **R** Maybe pine cones close when it rains so they stay dry and don't get damaged. |
| f-022 | Why are some caves cold? | **P** I think some caves are cold because they're deep underground, where it's very cold and the sun doesn't shine. | (abstain) | **F** Maybe the air is colder at higher places, so caves near mountains get cold. |
| f-023 | Why is mud sticky? | **P** I think mud is sticky because it has water in it. | **W** I think mud is sticky because it has a special kind of stuff inside that makes it stick to things. | **P** Maybe mud is sticky because it has a lot of water and the water makes it feel thick and sticky. |
| f-024 | Why do some leaves feel fuzzy? | **R** I think some leaves feel fuzzier because they have lots of tiny hairs on them. | **F** I think the fuzzy leaves might be from the wind or the cold, and they help the tree stay warm. | **P** Maybe the fuzzy leaves help keep the air around them warm and soft. |
| f-025 | Why are some lakes green? | **P** I think some lakes are green because they have plants in them, like watercress. | **R** I think some lakes are green because of the green stuff in the water, like from algae. | **P** I think some lakes are green because the plants in the water make food from sunlight. |
| f-026 | Why does a rainbow have a curve? | (abstain) | (abstain) | **P** Maybe the rainbow has a curve because light splits into colors when it goes through water drops. |
| f-027 | Why do leaves have veins? | **P** I think leaves have veins to help them get water and food from the sun. | **F** I think leaves have veins like a map, so the green stuff can go to the middle of the leaf. | **P** Maybe the veins help the leaves get water and make the green stuff in the leaves. |
| f-028 | Why does a puddle look like a mirror? | (abstain) | (abstain) | **F** Maybe when the water gets cold, it turns into tiny drops and looks like a mirror. |
| f-029 | Why are some clouds pink? | **W** I think some clouds are pink because they're full of tiny water drops that make pretty colors. | (abstain) | **R** Maybe the pink clouds are just the red and orange light from the sun. |
| f-030 | Why do acorns have little hats? | **P** I think the little hats on acorn trees help protect the acorns from rain and sun. | **P** I think the little hats on acorns help them stay dry and keep the sun from drying them out. | **P** Maybe acorn hats help keep the acorns dry and safe. |
| f-031 | Why do some berries make you sick? | (abstain) | **P** I think some berries make you sick because they are not ripe or they have bad germs. | (abstain) |
| f-032 | Why is space dark? | **W** I think space is dark because it's empty, and nothing can shine light through it. | **P** I think space is dark because it has no air or clouds to let light through. | **F** Maybe space is dark because it has no stars or light to shine on. |
| f-033 | Why does the moon look orange sometimes? | (principle:moon_phases) | (principle:moon_phases) | (principle:moon_phases) |
| f-034 | Why do astronauts wear big suits? | **P** I think the big suits help keep astronauts safe and dry in space. | (abstain) | (abstain) |
| f-035 | Why do rockets need fire? | **W** I think rockets need fire to make them fly. | **W** I think rockets need fire to go up into the sky, like a big hot fire. | **W** Maybe rockets need fire to go up into the sky and make a big flying trip. |
| f-036 | Why is Jupiter so big? | (abstain) | **P** I think Jupiter is big because it has a lot of gas and it spins fast. | **P** Maybe Jupiter is big because it has a big ball of gas that makes it huge. |
| f-037 | Why do stars have points in drawings? | (abstain) | **W** I think stars have points in drawings because they look like little stars in the sky. | **W** Maybe stars have points in drawings because they are like little dots that show where they are in the sky. |
| f-038 | Why does the moon have a face? | **F** I think the moon has a face because it's always round, like a circle. | **W** I think the moon has a face because it bounces sunlight back to us. | **W** Maybe the Moon has a face because it bounces back sunlight, and that's how we see its shape. |
| f-039 | Why do astronauts eat food from bags? | **F** I think the bags are like a soft, comfy chair for their tummies. | (abstain) | (abstain) |
| f-040 | Why does the moon make the sea move? | **R** I think the moon makes the sea move because it pulls on the water, like a big rubber band. | (abstain) | **F** Maybe the Moon pulls the sea with its light, like a big invisible hand. |
| f-041 | Why does the toast pop up? | (abstain) | **F** I think the toast pops up because it gets hot and bakes inside the oven. | **F** Maybe the toast gets hot and the air inside pops up. |
| f-042 | Why does the vacuum cleaner make noise? | (abstain) | (abstain) | **R** I think the fan pulls air into the machine, which makes it make noise. |
| f-043 | Why does the floor feel cold in the morning? | **F** I think the floor feels cold in the morning because it was sleeping all night. | **R** I think the floor feels cold in the morning because the sun hasn't warmed it yet. | **R** Maybe the floor feels cold in the morning because the sun has not warmed it yet. |
| f-044 | Why does a door squeak? | **W** I think a door squeaks because it is moving. | **W** I think a door squeaks because something is moving back and forth, like a little toy. | **P** Maybe a door squeaks when it is not fixed well and the wood is loose. |
| f-045 | Why do rubber bands snap back? | (abstain) | **R** I think rubber bands snap back because they are stretchy and want to go back to the way they were. | (abstain) |
| f-046 | Why does the oven get hot? | (kb) | (kb) | (kb) |
| f-047 | Why do pots have handles? | **R** I think handles make it easier to carry a pot, like how you hold your drink. | **R** I think pots have handles so we can hold them safely when we cook. | **R** Maybe pots have handles to help us hold them when we cook or move them. |
| f-048 | Why do keys open locks? | **P** I think keys are tools that fit into locks to make them work. | **W** I think keys open locks because they fit into the lock like a key fits into a lock. | **R** Maybe keys open locks by fitting into the lock's shape and turning it. |
| f-049 | Why do my crayons break? | **F** I think the crayon is made of a soft material that gets hard when it's used, so it breaks easily. | **F** I think crayons break because they get too hot or too cold, and they get too soft. | **P** Maybe crayon breaks when you don't use it right, like when you drop it or it gets too hot. |
| f-050 | Why does paper turn yellow? | **P** I think paper turns yellow because it gets old and used up. | **F** I think paper turns yellow because it gets old and loses its green stuff. | **W** I think paper can turn yellow because it is not kept dry or clean. |
| f-051 | Why are there holes in cheese? | **P** I think holes in cheese are made by tiny living things called tiny tiny bugs. | **F** I think the holes in cheese come from yeast in the dough. | (abstain) |
| f-052 | Why do people shake hands? | **W** I think most people use their right hand more, so they shake hands with it. | **R** I think people shake hands to say hello or say goodbye. | **R** I think people shake hands to say hello or show they're not angry. |
| f-053 | Why do we have to raise our hand in class? | (abstain) | (abstain) | (abstain) |
| f-054 | Why do we clap at the end of a show? | **W** I think we like to feel happy after a show, so clapping makes us feel better. | (abstain) | (abstain) |
| f-055 | Why do people put flags on buildings? | **P** I think flags on buildings are like team flags, to show who the building belongs to. | **P** I think people put flags on buildings to show their team or group, like a special sign. | **P** I think people put flags on buildings to show their team or group. |
| f-056 | Why do we have to share toys? | (chat, A canned) | (chat) | (chat) |
| f-057 | Why do grown-ups go to work? | **R** I think grown-ups go to work because they need money to buy food and clothes. | **R** I think grown-ups go to work to make money to buy food and toys. | **R** Maybe grown-up people go to work because they need to earn money or help others. |
| f-058 | Why do we send letters? | **R** I think we send letters to share our thoughts and ideas with others. | (abstain) | **R** I think because letters help us talk to friends and family. |
| f-059 | Why do people wave hello? | **R** I think people wave hello because it's a friendly way to say hello and make others feel happy. | (abstain) | **R** I think because they want to say hello to someone they know. |
| f-060 | Why do we have to knock on doors? | (abstain) | (abstain) | (abstain) |
| f-061 | Why do we have weekends? | (abstain) | **R** I think weekends are for fun and rest, so we can play and go to the park. | **F** Maybe we have weekends to enjoy the fun things that happen in the summer. |
| f-062 | Why do we have to be quiet in the library? | (chat, W (quiet = stay safe)) | (chat) | (chat) |
| f-063 | Why do people give presents? | **R** I think people give presents to make others happy and feel loved. | **R** I think people give presents to show they care for someone. | **R** I think people give presents to show how much they care and love. |
| f-064 | Why my hair is black? I want a blonded hair | **R** I think your hair is black because it has a special kind of hair stuff that makes it look dark. | **F** I think your hair is black because it has a special kind of green stuff in it. | **F** I think hair is made of a hard stuff that helps it grow and look the way you want. |
| f-065 | why i need to go to bed at 10 | (chat, A canned) | (chat) | (chat) |
