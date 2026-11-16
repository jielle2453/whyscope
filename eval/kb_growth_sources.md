# Knowledge growth: where the new topics came from (2026-11-15)

Goal: more curated entries for questions young children ask often, chosen from public lists, not from our own test sets
(`eval/heldout_en_v2.jsonl`, `heldout_en_v3*.jsonl` and `kid_questions.jsonl` were not opened for this work).

## Public lists of frequent kid questions (used to pick topics)

- 100 easy "why" questions for students (many everyday topics: animals, body, sky, food, objects, society): https://www.omtexclasses.com/2025/06/100-easy-why-questions-for-students.html
- Home Science Tools, "Science questions kids ask" (sky, moon in daytime, airplanes, rainbows, rocks, germs, plants): https://learning-center.homesciencetools.com/article/top-science-questions-kids-ask/
- Science Sparks, "Science questions for kids" (35 questions: sloths, bamboo, bubbles, Mars, craters, Pluto, day and night, leap years): https://science-sparks.com/science-questions-for-kids
- Live Science, the questions UK children ask most (moon in the daytime, blue sky, aliens, weight of the Earth, how planes stay up) and Britannica's "Why?" and "First Big Book of Why" tables of contents, as summarised in web search results (the Live Science page itself could not be read): https://www.livescience.com/18099-questions-kids-parents.html

Topics already covered by an existing entry (`knowledge/entries`) or a principle (`knowledge/principles/principles.json`) were skipped
(for example buoyancy, gravity, magnets, echo, rainbow, seasons, day and night, moon phases, germs, teeth, sleep, volcanoes, earthquakes).

## Pages the facts were read from

Facts were taken from the pages below with a page-reading tool that returns a short summary of the page; wording is paraphrased,
nothing is copied. Where a page did not state a fact, the entry does not either (the review sheet lists the gaps).
The per-entry source is in each entry's `source_url` and in `knowledge/REVIEW_NEW_ENTRIES.md`.

- Simple English Wikipedia (CC BY-SA 4.0), most entries.
- NASA Space Place (sun, black holes, aurora, craters).
- NOAA Ocean Service (tides).
- National Geographic Kids (zebra, kangaroo, elephant).
- KidsHealth (bones, scab).

Several pages that were tried returned errors (NASA Space Place day and night, meteors, Mars, Saturn; NOAA ocean color and salt; USGS cloud and raindrop pages; Britannica Kids dog; KidsHealth dreams, crying, vegetables).
Topics that depended on those pages were either re-sourced from Simple English Wikipedia or dropped.

## Result

114 new entries, all `"draft": "ai"` and `"reviewed_by": ""`: animals 21, body 18, sky and weather 19 (sky, space, weather, sea),
plants 8, food 7, machines and everyday objects 17, water and physics 3 (new topic `physics`), earth and rocks 11 (new topic `earth`),
people and society 10 (new topic `people`).
