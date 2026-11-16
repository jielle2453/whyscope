# Principle library: review sheet (English)

Status: AI draft. A human must check every row before `reviewed_by` is filled in.

How to review: for each row write `OK`, or `fix: <what is wrong / the corrected sentence>` in the last column.
- Facts must be TRUE and simple (a 5-8 year old, conservative wording).
- Every answer must be true for EVERY item in the principle's "Applies to" list (`{object}` is replaced by one of them).
  If an item makes an answer false or silly, write the item name in the fix column.
- `partial` principles give only the general area, not the full reason, so the answers must stay modest.
- No device feelings, no flattery, no jargon (the voice rules are checked by `python scripts/check_principles.py`).
- Chinese text is in the JSON (`*_zh`) and needs a separate zh-TW check.

Principles: 71

## 1. Floating and sinking (`buoyancy`)

Applies to: boat, ship, ice cube, rubber duck, swim ring, log, cork, rock, coin, pebble, beach ball, raft, toy boat, apple, wood block, stone

| Kind | Text | OK / fix |
|---|---|---|
| fact | Water pushes things up. This push is called buoyancy. | |
| fact | A thing that is lighter than the same amount of water floats. | |
| fact | A thing that is heavier than the same amount of water sinks. | |
| fact | Things with air inside, like swim rings and boats, float more easily. | |
| answer | Water pushes up on the {object}. If it is light for its size, it floats. | |
| answer | A thing that is light for its size floats. A heavy one sinks. | |
| answer | Water pushes up on things. Things with air inside float more easily. | |

## 2. Gravity (`gravity`)

Applies to: ball, apple, rain, raindrop, snowflake, leaf, pencil, toy, book, shoe, waterfall, spoon, acorn, crumb, cup, paper

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Earth pulls things down. This pull is called gravity. | |
| fact | That is why things fall to the ground when you let go. | |
| fact | Gravity keeps us and everything else on the ground. | |
| fact | The Moon pulls less than the Earth, so things feel lighter there. | |
| answer | The Earth pulls the {object} down. | |
| answer | The {object} comes down because the Earth pulls on it. | |
| answer | The Earth pulls everything toward the ground. | |

## 3. Friction (rubbing and slowing) (`friction`)

Applies to: shoe, ice, brake, slide, bike tire, car tire, sled, carpet, wet floor, sandpaper, rope, door mat, boot

| Kind | Text | OK / fix |
|---|---|---|
| fact | When two things rub together, a push-back slows the movement. It is called friction. | |
| fact | Rough surfaces have more friction. Slippery surfaces have less. | |
| fact | Rubbing makes things warm, and it slowly stops sliding things. | |
| answer | When things rub together, friction slows them down. | |
| answer | Rough things rub more. Slippery things rub less. | |
| answer | Things rub on the {object}, so they slow down. | |

## 4. Magnets (`magnets`)

Applies to: nail, paper clip, plastic toy, paper, needle, wooden spoon, screw, foil, rubber band, glass cup, scissors, fridge door, iron pan

| Kind | Text | OK / fix |
|---|---|---|
| fact | A magnet pulls on things that have iron in them, like nails and paper clips. | |
| fact | A magnet has two ends. Two of the same ends push apart, and two different ends pull together. | |
| fact | A magnet can pull on a thing without touching it. | |
| fact | Not everything sticks to a magnet. Paper and plastic do not. | |
| answer | Magnets pull on things that have iron in them. | |
| answer | A magnet sticks to the {object} only if it has iron. | |
| answer | Magnets can pull from a little way off. They pull on iron. | |

## 5. Sound and shaking (`sound`)

Applies to: drum, guitar string, speaker, bell, whistle, radio, horn, triangle, piano, flute, rubber band, cymbal, car horn, alarm

| Kind | Text | OK / fix |
|---|---|---|
| fact | When something shakes back and forth (vibrates), it makes a sound. | |
| fact | Sound travels through the air to our ears. | |
| fact | Fast shaking makes a high sound. Slow shaking makes a low sound. | |
| fact | Big shaking makes a loud sound. | |
| answer | The {object} shakes very fast, and that makes the sound. | |
| answer | Sounds come from shaking. The {object} shakes, and the air carries the sound to you. | |
| answer | Fast shaking makes high sounds. Slow shaking makes low sounds. | |

## 6. Echoes (`echo`)

Applies to: tunnel, canyon, cave, empty room, bathroom, mountain, big hall, gym, well, stairwell, valley, long hallway, church, tiled room

| Kind | Text | OK / fix |
|---|---|---|
| fact | Sound bounces off hard, flat things, like walls and cliffs. | |
| fact | The bounced sound comes back to our ears a moment later. That is an echo. | |
| fact | Soft things, like curtains and carpets, soak up sound, so there is less echo. | |
| answer | Sound bounces off hard walls. In the {object}, it comes back to your ears. | |
| answer | That is an echo. Your sound hits a hard wall and bounces back to you. | |
| answer | Hard, flat walls bounce sound back. That is why the {object} has an echo. | |

## 7. Light and shadows (`light_shadow`)

Applies to: tree, house, hand, wall, umbrella, curtain, tent, cardboard box, puppet, bird, cloud, building, fence, person

| Kind | Text | OK / fix |
|---|---|---|
| fact | Light travels in straight lines. | |
| fact | When something blocks the light, a shadow appears behind it. | |
| fact | Light goes through clear things like glass, but not through solid things like wood. | |
| fact | The closer the light is to the object, the bigger the shadow. | |
| answer | The {object} blocks the light. So there is a shadow behind it. | |
| answer | Light goes in straight lines. It cannot bend around things. | |
| answer | Light goes through clear things, like glass. It cannot go through wood. | |

## 8. Mirrors and bouncing light (`reflection`)

Applies to: mirror, puddle, lake, spoon, car mirror, window at night, shiny pot, bike reflector, vest, foil, bathroom mirror, polished floor

| Kind | Text | OK / fix |
|---|---|---|
| fact | When light hits a shiny thing, it bounces back. | |
| fact | A mirror is very smooth, so it bounces the light back neatly and we see ourselves. | |
| fact | White things bounce back a lot of light. Black things take in more light. | |
| fact | We see things because light bounces off them into our eyes. | |
| answer | Light bounces off the {object} and back to your eyes. | |
| answer | Shiny, smooth things bounce light back. The {object} is like that. | |
| answer | We see things when light bounces off them into our eyes. | |

## 9. Many colors in light (rainbows) (`light_colors`)

Applies to: soap bubble, CD, crystal, prism, garden hose spray, oil puddle, fountain spray, sprinkler, raindrop, water drop, glass prism, waterfall mist

| Kind | Text | OK / fix |
|---|---|---|
| fact | Sunlight looks white, but it has many colors hidden inside. | |
| fact | When light goes through tiny drops of water, the colors spread apart and make a rainbow. | |
| fact | Rainbows are easiest to see when the sun comes out after rain. | |
| fact | A rainbow shows colors from red at one edge to violet at the other. | |
| answer | Sunlight has many colors hidden in it. Water drops spread them apart. | |
| answer | Light hits the {object}, and the colors spread out. | |
| answer | White light is made of many colors. Water or glass can show them. | |

## 10. Light bends in water and glass (`refraction`)

Applies to: spoon in water, straw in a drink, pencil in water, fish bowl, swimming pool, glass of water, pond, bathtub, fish tank, cup of water

| Kind | Text | OK / fix |
|---|---|---|
| fact | Light bends when it goes from water into air, or from glass into air. | |
| fact | Our eyes think light comes straight, so a thing in water looks bent or in the wrong place. | |
| fact | A magnifying glass and glasses bend light on purpose to help us see. | |
| answer | Light bends in water, so the {object} looks different. | |
| answer | Your eyes think light comes straight. Bent light tricks them. | |
| answer | Water and glass bend light. A magnifying glass bends it to make things look big. | |

## 11. Blue sky and red sunsets (`sky_color`) [partial]

Applies to: blue sky, sky, sunset, sunrise, red sky, orange sky, evening sky, morning sky, daytime sky, setting sun, sky at noon, rising sun, sky color, dusk

| Kind | Text | OK / fix |
|---|---|---|
| fact | Sunlight has many colors in it. | |
| fact | The air bounces blue light around the whole sky, so the sky looks blue. | |
| fact | At sunrise and sunset, the sunlight travels through more air. | |
| fact | Most of the blue is bounced away on the way, so we see red and orange. | |
| answer | Sunlight has many colors. The air bounces the blue around the sky. | |
| answer | At sunset, light goes through lots of air. Blue bounces away, and red stays. | |
| answer | Blue light bounces around the sky more than red light. | |

## 12. Heat moves from hot to cold (`heat_flow`)

Applies to: hot soup, ice cream, metal spoon, coat, hot water bottle, cup of cocoa, cold drink, blanket, metal slide, hot bath, tea, pizza, hot chocolate, wooden spoon, ice pack, warm hands

| Kind | Text | OK / fix |
|---|---|---|
| fact | Heat moves from a hot thing to a cooler thing. | |
| fact | Hot soup left out slowly gives its heat to the air, so it cools down. | |
| fact | A cold thing left out takes heat from around it, so it slowly gets warmer. | |
| fact | Metal passes heat quickly, so it feels colder than wood to touch. | |
| answer | Heat moves from hot things to cooler things. The {object} gives or takes heat from nearby things. | |
| answer | Heat always moves toward the cooler thing. | |
| answer | Warm things give heat away to cooler things around them. | |

## 13. Melting and freezing (`melt_freeze`)

Applies to: ice cube, ice cream, chocolate, snow, candle wax, ice pop, butter, snowman, crayon, icicle, frozen puddle, ice on a pond, cheese, popsicle, snowball, ice block

| Kind | Text | OK / fix |
|---|---|---|
| fact | When water gets cold enough, it freezes into ice. | |
| fact | When ice gets warm, it melts into water. | |
| fact | Many things, like chocolate and candle wax, also soften and melt when they are warm. | |
| answer | When the {object} gets warm enough, it melts. | |
| answer | Heat makes some things soft and runny. Cold makes them hard again. | |
| answer | Water freezes into ice when it gets cold enough. Warm ice melts. | |

## 14. Drying up (water goes into the air) (`evaporation`)

Applies to: wet clothes, puddle, wet hair, wet hands, sweat, wet road, wet towel, laundry, wet footprint, spilled water, wet swimsuit, wet sidewalk, wet dog, wet sand, wet paper, wet shoe

| Kind | Text | OK / fix |
|---|---|---|
| fact | Water slowly turns into invisible water in the air. This is called drying up. | |
| fact | Sun and wind make water dry faster. | |
| fact | When the water goes away, things in it, like salt, stay behind. | |
| answer | The water in the {object} slowly goes into the air. You cannot see it. | |
| answer | Water turns into invisible water in the air. Sun and wind help it go faster. | |
| answer | The {object} dries because its water floats away into the air. | |

## 15. Water drops on cold things (`condensation`)

Applies to: drink glass, window, bathroom mirror, pot lid, bottle, can, car window, mirror, glasses, ice water glass, glass window, cup

| Kind | Text | OK / fix |
|---|---|---|
| fact | The air has invisible water in it. | |
| fact | When this water touches a cold thing, it turns back into tiny drops. | |
| fact | That is why a cold drink glass gets wet outside and windows fog up on cold days. | |
| answer | Water in the air makes drops on the cold {object}. | |
| answer | Invisible water in the air turns into drops on cold things. | |
| answer | The drops come from the air, not from the {object}. | |

## 16. Where rain and water come from (`water_cycle`)

Applies to: rain, raindrop, puddle, river, sea, lake, snow, stream, ocean, rainstorm, pond, rain cloud, waterfall, creek, drizzle, rainwater

| Kind | Text | OK / fix |
|---|---|---|
| fact | The sun warms water in the sea, rivers and ground, and it rises into the air. | |
| fact | High in the sky it cools and turns into tiny drops that gather as clouds. | |
| fact | When the drops in a cloud get big and heavy, they fall as rain. | |
| fact | The rain flows to rivers and the sea, and the water travels again. | |
| answer | The sun warms water, and it rises into the sky. Cold air turns it into clouds. | |
| answer | Cloud drops get big and heavy, and fall as rain. Then the water travels again. | |
| answer | The water in the {object} goes up and comes down again. | |

## 17. Clouds (`clouds`)

Applies to: cloud, white cloud, dark cloud, fluffy cloud, rain cloud, storm cloud, gray cloud, big cloud, thick cloud

| Kind | Text | OK / fix |
|---|---|---|
| fact | A cloud is made of billions of tiny drops of water. | |
| fact | The drops are so small and light that moving air holds them up. | |
| fact | Clouds look white because the drops bounce light around. | |
| fact | Thick clouds look dark because less light gets through them. | |
| answer | A cloud is made of tiny drops of water. They are so light that air holds them up. | |
| answer | The {object} is full of tiny water drops. Wind moves it along. | |
| answer | Tiny drops bounce light, so a cloud looks white. A thick cloud looks dark. | |

## 18. Snow and frost (`snow_freezing`)

Applies to: snow, snowflake, snowman, snowball, icicle, frost, mountain snow, fresh snow, snow on a mountain, ice on a window

| Kind | Text | OK / fix |
|---|---|---|
| fact | Snow is frozen water. It forms when clouds are cold enough to freeze the tiny drops. | |
| fact | Snowflakes are tiny ice crystals that stick together. | |
| fact | Snow looks white because the ice bounces all the light back. | |
| fact | The air is colder high up, so mountain tops often have snow. | |
| answer | The {object} is frozen water. Water freezes when the air is cold enough. | |
| answer | Snow forms when clouds are cold. Tiny drops freeze and stick together. | |
| answer | Snow looks white because tiny ice bits bounce the light back. | |

## 19. Solids, liquids and gases (`states_of_matter`)

Applies to: ice, water, rock, juice, milk, honey, air, block, toy brick, oil, table, balloon air, soup, stone, pillow, paint

| Kind | Text | OK / fix |
|---|---|---|
| fact | A solid keeps its own shape, like a rock or a block. | |
| fact | A liquid flows and takes the shape of its cup, like water or juice. | |
| fact | A gas, like air, is usually invisible and spreads everywhere. | |
| fact | The same thing can be a solid, liquid or gas depending on how hot it is. | |
| answer | Things are solids, liquids or gases. The {object} is one of those. | |
| answer | A solid keeps its shape. A liquid flows and a gas spreads out. | |
| answer | Rocks are solids, water is a liquid and air is a gas. | |

## 20. Air takes up space (`air`)

Applies to: balloon, bike tire, ball, swim ring, bubble, beach ball, air mattress, football, basketball, pool toy, soap bubble, car tire, bouncy castle, air pillow, party balloon

| Kind | Text | OK / fix |
|---|---|---|
| fact | Air is everywhere, even though we cannot see it. | |
| fact | Air takes up space and has a little weight. | |
| fact | When you blow up a balloon, the air inside pushes it big. | |
| fact | We and many living things need air to live. | |
| answer | Air is everywhere, but we cannot see it. It takes up space inside the {object}. | |
| answer | Air inside the {object} pushes out and keeps it round. | |
| answer | You cannot see air, but it is real. It fills things up and makes them big. | |

## 21. Wind (`wind`)

Applies to: kite, windmill, sailboat, flag, leaf, tree branch, hat, umbrella, wind chime, dandelion seed, pinwheel, paper, sail, cloud, grass, curtain

| Kind | Text | OK / fix |
|---|---|---|
| fact | Wind is air that is moving. | |
| fact | The sun warms some places more than others, and the air moves between warm and cool places. That makes wind. | |
| fact | Wind can move leaves, kites and sailboats. | |
| answer | Wind is air that moves. It can push the {object} along. | |
| answer | The sun warms some places more. Air flows from cool places to warm places, and that is wind. | |
| answer | You cannot see wind, but you see the {object} move. | |

## 22. Dissolving in water (`dissolving`)

Applies to: sugar, salt, sand, drink powder, bath bomb, cocoa powder, stone, rock, honey, jelly powder, vitamin tablet, coffee powder, pebble, soap, sugar cube, gravel

| Kind | Text | OK / fix |
|---|---|---|
| fact | Some things, put in water, get smaller and mix in until we cannot see them. This is called dissolving. | |
| fact | Sugar and salt dissolve in water, but sand and stones do not. | |
| fact | Hot water usually dissolves sugar faster. | |
| fact | The dissolved stuff is still there, just in very tiny bits. | |
| answer | Some things mix into water and get too tiny to see. That is dissolving. | |
| answer | Sugar and salt dissolve in water, but sand and stones do not. | |
| answer | Hot water usually dissolves sugar faster. | |

## 23. Cooking changes food (`heat_changes`)

Applies to: egg, cake batter, bread dough, rice, potato, toast, pancake batter, cookie dough, sweet potato, fried egg, noodles, pizza dough, pancake, boiled egg, baked cake, muffin

| Kind | Text | OK / fix |
|---|---|---|
| fact | Some things are changed by heat into something new, and they cannot change back. | |
| fact | A raw egg gets hard when cooked, and cake batter becomes cake when baked. | |
| fact | Toast and fried food turn brown and smell good when heated. | |
| fact | Some food needs cooking to taste good and be safe. | |
| answer | Heat changes the {object} into something new. It cannot change back. | |
| answer | When you cook the {object}, heat changes it for good. | |
| answer | Cooking changes food for good. That makes it softer or harder, and it tastes better. | |

## 24. Why things are made of certain materials (`materials`)

Applies to: rain boots, pot, window, plastic bag, towel, paper, umbrella, chair, spoon, sponge, glass bottle, rubber ball, tire, mug, metal pan

| Kind | Text | OK / fix |
|---|---|---|
| fact | Different materials have different properties, like hard, soft, bendy, waterproof or clear. | |
| fact | People pick the right material for each job. | |
| fact | Rubber is waterproof and stretchy, so it is used for rain boots and tires. | |
| fact | Glass is clear, so it is used for windows. | |
| answer | People pick a material that is good for the job. | |
| answer | The {object} is made from something that works well. | |
| answer | Soft, hard, bendy or clear: each one is good for something. | |

## 25. How flying things stay up (`flying`)

Applies to: bird, airplane, bee, bat, paper airplane, butterfly, eagle, seagull, glider, pigeon, dragonfly, owl, sparrow, duck, jet, fly

| Kind | Text | OK / fix |
|---|---|---|
| fact | Wings push air down, and the air pushes the wings up. | |
| fact | A bird flaps its wings to push the air. | |
| fact | A plane's engines push it forward fast, so air flows over its wings and holds it up. | |
| fact | A flying animal is also light for its size. | |
| answer | Wings push air down, and the air pushes the {object} up. | |
| answer | Its wings push air down, so the {object} stays up. | |
| answer | Wings push on the air, and the air pushes back. That holds things up. | |

## 26. Electricity and circuits (`circuits`)

Applies to: light switch, flashlight, toy car with batteries, lamp, light bulb, doorbell, night light, remote control, toy robot, electric fan, radio, clock, string lights, toy train, toy with batteries, lantern

| Kind | Text | OK / fix |
|---|---|---|
| fact | Electricity needs a full loop to travel around (a circuit) to light a lamp or make something work. | |
| fact | A switch closes or opens the loop. | |
| fact | A battery can send electricity to a small bulb or motor. | |
| fact | Electricity can be dangerous, so children should never play with sockets. | |
| answer | Electricity needs a full loop to go around. Then the {object} can work. | |
| answer | A switch opens or closes the loop. | |
| answer | Electricity is dangerous. Never touch a socket. | |

## 27. Static electricity (`static`)

Applies to: balloon, hair, ruler, sweater, comb, hat, wrap, slide, carpet, blanket, cat fur, sock

| Kind | Text | OK / fix |
|---|---|---|
| fact | When two things rub together, they can get a little static electricity. | |
| fact | A thing with static can pull on small bits of paper or hair. | |
| fact | On dry days there is more static, so you may get a little zap when you touch something. | |
| answer | Static can build up on the {object}. | |
| answer | Rubbing makes static. Static can make hair stand up or give a tiny zap. | |
| answer | Static electricity is a tiny pull that comes from rubbing things. | |

## 28. Pushes and pulls (`forces_motion`)

Applies to: ball, toy car, swing, football, door, heavy box, wagon, shopping cart, sled, wheelbarrow, bowling ball, rolling ball, drawer, stroller, toy truck, soccer ball

| Kind | Text | OK / fix |
|---|---|---|
| fact | A push or a pull can make something start moving, stop or turn. | |
| fact | A bigger push makes it go faster and farther. | |
| fact | Heavy things are harder to get moving. | |
| fact | A moving thing keeps going until another force stops it. | |
| answer | A push or pull makes the {object} move, stop or turn. | |
| answer | A bigger push makes the {object} go faster and farther. | |
| answer | A moving thing keeps going until something stops it. | |

## 29. Wheels, ramps and levers (`simple_machines`)

Applies to: wheel, ramp, seesaw, scissors, bottle opener, suitcase wheel, skateboard, wheelbarrow, crowbar, slide, bicycle wheel, stroller wheel, wagon wheel, door wedge, nutcracker, shopping cart wheel

| Kind | Text | OK / fix |
|---|---|---|
| fact | Wheels that roll make it easier to move something than dragging it along the ground. | |
| fact | A ramp lets us move a thing up slowly, which takes less effort. | |
| fact | A lever, like a seesaw, lets a small push lift something heavy. | |
| fact | People invented these simple machines to make work easier. | |
| answer | The {object} makes work less hard. | |
| answer | A wheel rolls, so things move with less push. | |
| answer | People made the {object} so heavy work takes less push. | |

## 30. The seasons (`seasons`)

Applies to: summer, winter, spring, autumn, fall, hot summer, cold winter, long summer day, short winter day, snowy winter, season, warm spring, cool autumn

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Earth goes around the sun once in a year. | |
| fact | The Earth is tilted, so through the year a place sometimes leans toward the sun and sometimes away. | |
| fact | Leaning toward the sun means longer days and warm weather, which is summer. Leaning away means shorter days and cold weather, which is winter. | |
| fact | Spring and autumn are in between. | |
| answer | The Earth is tilted as it goes around the sun. That gives us seasons. | |
| answer | In summer, our place leans toward the sun. In winter, it leans away. | |
| answer | The Earth is tilted, so we get the {object}. | |

## 31. Day and night (`day_night`)

Applies to: day, night, sunrise, sunset, morning, evening, dark night, dusk, dawn, midnight, noon, daytime, nighttime, twilight

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Earth spins like a top, once a day. | |
| fact | The side facing the sun has day, and the side facing away has night. | |
| fact | The sun is not walking across the sky. The Earth is turning, so the sun seems to rise and set. | |
| fact | When it is day on one side of the Earth, it is night on the other side. | |
| answer | The Earth spins once a day. When our side faces the sun, it is day. | |
| answer | The sun does not move. The Earth turns, so the sun seems to rise and set. | |
| answer | The {object} happens because the Earth spins around once each day. | |

## 32. Shadows change during the day (`sun_path`)

Applies to: long shadow, short shadow, morning shadow, noon shadow, evening shadow, afternoon shadow, shadow at sunset, sundial, my shadow, tree shadow, shadow on the ground, shadow of the house

| Kind | Text | OK / fix |
|---|---|---|
| fact | We see the sun rise in the east, go high at noon, and set in the west. | |
| fact | When the sun's place changes, shadows change too. | |
| fact | When the sun is high, shadows are short. When it is low, shadows are long. | |
| answer | The sun is low in the morning, so shadows are long. | |
| answer | At noon the sun is high, so shadows are short. | |
| answer | The {object} changes because the sun seems to move. | |

## 33. The Moon and its shapes (`moon_phases`)

Applies to: moon, full moon, crescent moon, half moon, new moon, bright moon, moon at night, daytime moon, moonlight, big moon, round moon, curved moon

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Moon does not make its own light. It bounces back sunlight. | |
| fact | The Moon goes around the Earth, about once a month. | |
| fact | From Earth we see different parts of its sunny side, so it looks round sometimes and curved other times. | |
| fact | The Moon seems to follow us because it is very far away. | |
| answer | The {object} shines because sunlight bounces off it. | |
| answer | The Moon goes around the Earth. We see more or less of its sunny side. | |
| answer | The Moon has no light of its own. It bounces light from the sun. | |

## 34. The Sun and the stars (`sun_and_stars`)

Applies to: sun, star, bright star, tiny star, night star, hot sun, big sun, little star, far star, North Star, shining star

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Sun is a star. It is closer to us, so it looks big and bright. | |
| fact | The stars at night are very, very far away suns, so they look tiny. | |
| fact | In the day the Sun is so bright that we cannot see the stars, but they are still there. | |
| fact | The Sun is a huge, very hot ball of gas that gives off light. | |
| answer | The Sun is a star. Night stars are suns that are very far away. | |
| answer | A star is a huge ball of very hot gas. | |
| answer | The {object} is a huge, hot ball of gas that shines. | |

## 35. The Sun warms things (`sun_warms`)

Applies to: sand, beach, sidewalk, car seat, window sill, rock, pavement, sunny spot, laundry, puddle, garden, roof, metal slide, desert, black car

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Sun gives the Earth light and heat. | |
| fact | Places in the sunshine get warm, so daytime is warmer than night. | |
| fact | Plants need sunlight to grow, and we need the Sun's warmth to live. | |
| fact | Too much sun can burn the skin, so we use sunscreen or wear hats. | |
| answer | The sun gives off light and heat. Sunshine warms the {object}. | |
| answer | Sunshine heats the {object}, so it feels warm in the day. | |
| answer | Too much sun can burn your skin. Wear a hat. | |

## 36. Lightning first, thunder later (`light_sound_speed`)

Applies to: lightning, fireworks, storm, lightning bolt, firework, flash of lightning, big storm, distant storm, lightning strike, summer storm

| Kind | Text | OK / fix |
|---|---|---|
| fact | Light travels much faster than sound. | |
| fact | Lightning and thunder happen together, but we see the light first and hear the sound later. | |
| fact | The farther away the storm is, the later the thunder arrives. | |
| fact | Lightning is a big spark of electricity from clouds, so during a storm we stay indoors. | |
| answer | Light is much faster than sound. We see the flash first and hear the boom later. | |
| answer | Lightning and its boom happen together. The light gets to us first. | |
| answer | The farther away the {object}, the later we hear it. | |

## 37. Going around the Sun and the Earth (`orbits`)

Applies to: Earth, Moon, planet, satellite, space station, Mars, Venus, Jupiter, Saturn, Mercury, Neptune, Uranus

| Kind | Text | OK / fix |
|---|---|---|
| fact | Gravity pulls things toward the Sun and the Earth. | |
| fact | The Earth and the other planets also move sideways very fast. | |
| fact | Pulled in and moving sideways, they keep circling instead of falling in. | |
| fact | The Earth takes one year to go around the Sun. The Moon takes about a month to go around the Earth. | |
| answer | Something big pulls the {object}. It also moves sideways, so it goes around. | |
| answer | It keeps moving sideways while the pull holds it. So it circles and does not fall in. | |
| answer | The Earth takes a year to go around the sun. | |

## 38. Floating in space (`weightless_space`)

Applies to: astronaut, space station, spaceship, space suit, floating pen, space shuttle, space food, space toy, floating water drop, space capsule, spacecraft

| Kind | Text | OK / fix |
|---|---|---|
| fact | Gravity is still there up where the space station flies. | |
| fact | The station and everything in it keep falling around the Earth together. | |
| fact | Falling together feels like floating. | |
| answer | The pull of the Earth is still there. The astronaut and ship keep falling around the Earth together. | |
| answer | The {object} floats because it keeps falling around the Earth. | |
| answer | Falling together feels like floating. | |

## 39. Why planets and stars are round (`planets_round`)

Applies to: Earth, Moon, Sun, planet, Mars, Jupiter, Venus, Saturn, star, Neptune, Mercury, Uranus

| Kind | Text | OK / fix |
|---|---|---|
| fact | Gravity pulls all the parts of a big thing toward its middle. | |
| fact | A big thing like a planet gets pulled into a round ball. | |
| fact | Small things, like tiny space rocks, are too small to be pulled round and can be lumpy. | |
| answer | Every part of the {object} is pulled toward its middle. That makes a round ball. | |
| answer | A very big thing pulls itself into a round ball. | |
| answer | Very big things end up round, like the Earth. | |

## 40. What plants need (`plant_needs`)

Applies to: plant, flower, tree, seedling, houseplant, grass, potted plant, cactus, sunflower, bean sprout, garden, lettuce, tomato plant, rose bush, vine, bush

| Kind | Text | OK / fix |
|---|---|---|
| fact | Plants need sunlight, water and air to grow. | |
| fact | A plant's leaves use sunlight, water and air to make their own food. | |
| fact | Leaves have a green part that helps make the food, which is why leaves are green. | |
| fact | A plant without light grows weak, and its leaves turn yellow. | |
| answer | The {object} needs sunlight, water and air to grow. | |
| answer | Plants make their own food in their leaves. They use sunlight, water and air. | |
| answer | Leaves have a green part that helps make food. That is why leaves are green. | |

## 41. Parts of a plant (`plant_parts`)

Applies to: root, stem, leaf, flower, trunk, branch, petal, fruit, tree trunk, tulip, rose, daisy, tree root, tree branch, flower stem, bud

| Kind | Text | OK / fix |
|---|---|---|
| fact | Roots hold the plant in the soil and take in water. | |
| fact | The stem carries water up to the leaves and holds the plant up. | |
| fact | Leaves make food. | |
| fact | Flowers make fruits and seeds. Many are bright and sweet-smelling to attract bees and butterflies. | |
| answer | Each part of a plant has a job. Roots drink water and stems carry it up. | |
| answer | The {object} has a job. It helps the plant. | |
| answer | Many flowers smell sweet and look bright to bring bees and butterflies. | |

## 42. Seeds and growing (`seeds_growth`)

Applies to: seed, bean, sunflower seed, acorn, watermelon seed, apple seed, pumpkin seed, bean sprout, sprout, seedling, pea, orange seed, peach pit, grass seed, tomato seed

| Kind | Text | OK / fix |
|---|---|---|
| fact | Many plants grow from seeds. | |
| fact | A seed sprouts when it has water, warmth and air. | |
| fact | The sprout grows into a seedling and then a big plant, which makes new seeds. | |
| fact | Fruits usually have seeds inside, and the seeds can grow into new plants. | |
| answer | A seed has a tiny new plant inside. With water and warmth, it sprouts. | |
| answer | The {object} can grow if it has water and warmth. | |
| answer | A sprout grows into a plant. The plant then makes new seeds. | |

## 43. Leaves change color and fall (`plants_change_year`)

Applies to: autumn leaf, red leaf, yellow leaf, maple leaf, fallen leaf, leaf pile, bare tree, ginkgo leaf, orange leaf, autumn tree, dry leaf, brown leaf

| Kind | Text | OK / fix |
|---|---|---|
| fact | In fall, many trees stop making the green stuff in their leaves. | |
| fact | Then the yellow and orange colors that were hidden show up. | |
| fact | Many trees drop their leaves for the cold winter and grow new ones in spring. | |
| answer | In fall, many trees stop making green. Other colors, like yellow and orange, show. | |
| answer | Many trees drop their leaves in winter. New leaves grow in spring. | |
| answer | The {object} changes as the tree gets ready for winter. | |

## 44. Bees, honey and flowers (`bees_pollination`)

Applies to: bee, honeybee, bumblebee, honey, honeycomb, beehive, hive, nectar, pollen, flower, garden flower

| Kind | Text | OK / fix |
|---|---|---|
| fact | Bees drink a sweet juice called nectar from flowers. | |
| fact | They carry the nectar home and turn it into honey to eat. | |
| fact | Flower dust (pollen) sticks to bees and gets carried to other flowers. | |
| fact | That helps flowers make seeds and fruits. | |
| answer | Bees drink sweet nectar from flowers. They turn it into honey to eat. | |
| answer | Bees and flowers help each other. The bee gets food, and the flower gets help making seeds. | |
| answer | The {object} is part of how bees and flowers work together. | |

## 45. Animal bodies fit their lives (`animal_adaptations`) [partial]

Applies to: giraffe neck, polar bear fur, camel hump, penguin feather, bird wing, fish fin, duck foot, cat claw, elephant trunk, owl eye, whale tail, rabbit ear, frog leg, bat wing, turtle shell, cheetah leg

| Kind | Text | OK / fix |
|---|---|---|
| fact | An animal's body is shaped in a way that helps it live. | |
| fact | A long neck can reach tall leaves, thick fur or fat keeps an animal warm, and wings let it fly. | |
| fact | Animals in different places have different bodies, like camels in the desert and bears in the Arctic. | |
| answer | The {object} helps the animal live where it lives. | |
| answer | Animal bodies are shaped to help them live. | |
| answer | Over a very long time, animals with helpful bodies lived on. | |

## 46. Animals in winter (sleeping and moving away) (`winter_animals`)

Applies to: bear, squirrel, goose, swallow, whale, monarch butterfly, bat, frog, chipmunk, duck, stork, bird flying south, hibernating bear, sleeping bat

| Kind | Text | OK / fix |
|---|---|---|
| fact | In winter it is cold and food is hard to find. | |
| fact | Some animals, like bears and bats, sleep a lot in winter and use less food. | |
| fact | Some animals, like many birds, fly or swim to a warmer place. | |
| fact | Some animals, like squirrels, store food before winter. | |
| answer | In winter, food is hard to find. So some animals sleep, and some go somewhere warm. | |
| answer | Some animals sleep through winter and some travel to warmer places. | |
| answer | Some animals save food before winter comes. | |

## 47. Animal homes and needs (`animal_homes_needs`)

Applies to: nest, burrow, den, rabbit hole, anthill, beehive, bird house, cave, hollow tree, mole hill, bird nest

| Kind | Text | OK / fix |
|---|---|---|
| fact | Animals need food, water, air and a safe place to live. | |
| fact | The place an animal lives is its habitat, like a forest, ocean or desert. | |
| fact | Many animals make homes, like nests and burrows, to stay safe and raise babies. | |
| answer | Animals need a safe place to live. The {object} keeps animals safe. | |
| answer | Many animals build a home to stay safe and raise their babies. | |
| answer | Animals need food, water, air and a safe home. The {object} gives some of that. | |

## 48. How animals grow up (`animal_life_cycle`)

Applies to: chick, caterpillar, tadpole, kitten, puppy, cub, duckling, calf, lamb, foal, baby bird, baby turtle, baby frog, baby bear, baby fish, bunny

| Kind | Text | OK / fix |
|---|---|---|
| fact | Animals have babies, the babies grow up, and then they have babies of their own. | |
| fact | Some animals hatch from eggs, like chickens and frogs. Others are born alive, like cats and dogs. | |
| fact | A caterpillar becomes a chrysalis, then a butterfly. | |
| fact | Animal parents often look after their babies. | |
| answer | The {object} will grow up. Grown-up animals have babies of their own. | |
| answer | Some baby animals come out of eggs. Others are born alive. | |
| answer | A caterpillar becomes a butterfly. A tadpole becomes a frog. | |

## 49. Why animals eat what they eat (`food_chain`)

Applies to: lion, rabbit, tiger, frog, shark, owl, snake, fox, deer, mouse, hawk, spider, cow, caterpillar, big fish, panda

| Kind | Text | OK / fix |
|---|---|---|
| fact | Plants make their own food. | |
| fact | Some animals eat plants, and some animals eat other animals. | |
| fact | When one eats another, we get a food chain. | |
| fact | Animals eat to get energy and to grow. | |
| answer | The {object} eats to get strength and to grow. | |
| answer | Plants make their own food. Some animals eat plants, and some eat other animals. | |
| answer | Every animal needs food for strength. That is why the {object} eats. | |

## 50. What is alive (`living_things`)

Applies to: rock, toy, robot, tree, bug, flower, fire, cloud, doll, river, car, plant, worm, ant, snowman

| Kind | Text | OK / fix |
|---|---|---|
| fact | Living things grow, and need water, food or nutrients, and air. | |
| fact | Living things have babies. | |
| fact | Rocks and toys are not alive, because they do not eat or grow. | |
| answer | To be alive, the {object} must grow, need food, and have babies. | |
| answer | Living things grow, need food and water, and have babies. Rocks and toys do not. | |
| answer | Plants and animals are alive. Rocks, toys and robots are not. | |

## 51. Animal sounds and signals (`animal_signals`) [partial]

Applies to: dog tail wag, cat purr, dog bark, cat meow, bird song, rooster crow, whale song, cricket chirp, wolf howl, cat tail, growl, lion roar, frog croak, bee dance, dog howl, duck quack

| Kind | Text | OK / fix |
|---|---|---|
| fact | Animals cannot talk like us, so they use sounds and body moves to tell others things. | |
| fact | A dog often wags its tail when it is excited or friendly. | |
| fact | A cat often purrs when it is calm. | |
| answer | Animals use sounds and moves to send messages. | |
| answer | Animals cannot talk like us. The {object} is one way they tell others something. | |
| answer | Animals send messages with sounds and body moves. The {object} is one of them. | |

## 52. How bodies cool down (`keeping_cool`)

Applies to: sweat, panting, dog tongue, wet shirt, fan, mud bath, elephant ear, wet towel, swimming, shade, cold shower

| Kind | Text | OK / fix |
|---|---|---|
| fact | Bodies make heat, and they must not get too hot. | |
| fact | People sweat, and dogs pant. Water on the skin or tongue dries and takes heat away. | |
| fact | A fan helps sweat dry faster, so you feel cooler. | |
| fact | Some animals cool off in water or mud. | |
| answer | When the body is hot, water on the skin or tongue dries. That takes heat away. | |
| answer | The {object} helps the body cool down. | |
| answer | Sweat and panting both cool the body as the water dries off. | |

## 53. Our senses (`senses`)

Applies to: eye, ear, nose, tongue, skin, fingertip, hand, foot, nostril, eyeball, taste bud, thumb

| Kind | Text | OK / fix |
|---|---|---|
| fact | We see with our eyes, hear with our ears, smell with our nose, taste with our tongue and feel with our skin. | |
| fact | Our eyes catch light and our ears catch sound, and they send messages to the brain. | |
| fact | The brain tells us what it is, and lets us feel cold, hot and pain. | |
| fact | Nose and tongue work together so we can taste food. | |
| answer | Your {object} sends messages to your brain. | |
| answer | We sense the world with eyes, ears, nose, tongue and skin. | |
| answer | The brain gets messages from your {object}. That is how you know what is around you. | |

## 54. Breathing and heartbeat (`breathing_heart`)

Applies to: heart, lung, muscle, leg, arm, body, chest, foot

| Kind | Text | OK / fix |
|---|---|---|
| fact | We breathe in air, which has the good air our body needs. | |
| fact | The heart is like a small pump that sends blood around the body. | |
| fact | When we run or play hard, the body needs more air, so we pant and the heart beats faster. | |
| fact | When we rest, breathing and heartbeat slow down. | |
| answer | When you run, your {object} works harder. | |
| answer | The heart is a pump that sends blood around your body. It beats faster when you play hard. | |
| answer | We breathe in air because the body needs it. We breathe harder when we run. | |

## 55. Why we eat (food and the body) (`food_digestion`)

Applies to: vegetable, apple, rice, bread, milk, meal, snack, breakfast, lunch, dinner, fruit, carrot, broccoli, egg, fish, soup

| Kind | Text | OK / fix |
|---|---|---|
| fact | Food gives the body strength and helps us grow. | |
| fact | Food is chewed in the mouth and goes to the tummy, and the body takes what it needs. | |
| fact | What is left over leaves the body as poop and pee. | |
| fact | When the tummy is empty, the body tells us we are hungry. | |
| answer | Your body uses the {object} for strength and to grow. | |
| answer | Food gives your body strength. What it cannot use leaves as poop and pee. | |
| answer | When your tummy is empty, your body says it is hungry. Then you eat. | |

## 56. Germs and washing hands (`germs_hygiene`)

Applies to: hand, doorknob, toilet, toy, floor, phone, pet, dirt, playground, shopping cart, money, handrail, table, sink, tissue, mask

| Kind | Text | OK / fix |
|---|---|---|
| fact | There are tiny, tiny germs we cannot see, and some of them can make us sick. | |
| fact | Washing hands with soap and water washes germs off. | |
| fact | We wash before eating and after using the toilet. | |
| fact | Cover coughs and sneezes with an elbow or tissue so germs do not reach other people. | |
| answer | Tiny germs we cannot see can make us sick. Soap and water wash them off. | |
| answer | Germs can be on the {object}. So we wash our hands. | |
| answer | Cover coughs and sneezes so germs do not reach other people. | |

## 57. Teeth and brushing (`teeth`)

Applies to: tooth, baby tooth, front tooth, back tooth, molar, loose tooth, new tooth, big tooth, wiggly tooth, bottom tooth, top tooth

| Kind | Text | OK / fix |
|---|---|---|
| fact | Teeth help us bite and chew food. | |
| fact | Germs in the mouth use sugar to make an acid that makes holes in teeth. We call these cavities. | |
| fact | Brushing every day cleans away the food bits and germs. | |
| fact | Baby teeth fall out and new big teeth grow in, but big teeth do not grow back. | |
| answer | Brushing cleans food and germs off your {object}. | |
| answer | Germs in your mouth use sugar to make acid. The acid can make holes in teeth. | |
| answer | Baby teeth fall out so big teeth can grow in. Big teeth do not grow back. | |

## 58. The body heals itself (`healing`)

Applies to: scab, cut, scrape, bruise, blister, bump, sore, bee sting, paper cut, knee scrape, bug bite, sunburn, bleeding cut, splinter hole

| Kind | Text | OK / fix |
|---|---|---|
| fact | When skin is cut and bleeds, the blood slowly dries and hardens over the cut. This is a scab. | |
| fact | A scab is like a little bandage that protects new skin growing underneath. | |
| fact | When the new skin is ready, the scab falls off by itself. | |
| fact | Do not pick at a scab, so the cut heals faster. | |
| answer | Your body fixes the {object} by itself. It takes a few days. | |
| answer | A scab is like a little bandage. New skin grows under it, and then it falls off. | |
| answer | Your body can heal itself. Do not pick at a scab, so it heals faster. | |

## 59. Sleep, rest and exercise (`sleep_exercise`) [partial]

Applies to: sleep, nap, bedtime, running, exercise, swimming, soccer, bike ride, jumping, playing outside, rest, gym class

| Kind | Text | OK / fix |
|---|---|---|
| fact | The body gets tired from using strength, and sleep lets it rest and grow. | |
| fact | With enough sleep, we have more energy and focus better the next day. | |
| fact | Exercise makes muscles and the heart stronger. | |
| fact | Scientists are still learning everything that sleep does. | |
| answer | Your body and brain rest and grow when you sleep. | |
| answer | The {object} is good for your body and brain. | |
| answer | Sleep helps you have more strength the next day. Exercise makes muscles and the heart strong. | |

## 60. Tastes: sour, sweet, salty and bitter (`taste_acids`)

Applies to: lemon, lime, orange, vinegar, sour candy, pickle, yogurt, green apple, sugar, candy, salt, bitter melon, coffee, chocolate, honey, ice cream

| Kind | Text | OK / fix |
|---|---|---|
| fact | Your tongue has tiny taste bumps that can taste sweet, sour, salty and bitter. | |
| fact | Lemons and vinegar taste sour because they have an acid in them. | |
| fact | Sugar tastes sweet, and salt tastes salty. | |
| fact | Smell helps taste, so food tastes plain when your nose is blocked. | |
| answer | Your tongue tastes the {object} with tiny taste bumps. | |
| answer | Your tongue can taste sweet, sour, salty and bitter. | |
| answer | Sour things, like lemons and vinegar, have an acid in them. | |

## 61. Wrinkly fingers in water (`wrinkly_fingers`) [partial]

Applies to: finger, toe, fingertip, thumb, hand, palm, foot, sole

| Kind | Text | OK / fix |
|---|---|---|
| fact | After a long time in water, the skin on fingers and toes wrinkles. | |
| fact | The body does this by itself. | |
| fact | Scientists think the wrinkles may help us grip wet things. | |
| answer | In water, the skin on your {object} wrinkles by itself. | |
| answer | Your body wrinkles the skin on fingers and toes by itself. It may help you grip wet things. | |
| answer | The wrinkles go away when your skin dries. | |

## 62. Balance and feeling dizzy (`balance_dizzy`) [partial]

Applies to: ear, inner ear, eye, brain, foot, leg, body, head, neck, ankle

| Kind | Text | OK / fix |
|---|---|---|
| fact | Inside our ears are tiny tubes with a little liquid. | |
| fact | The liquid moves when we move, and it tells the brain which way we are going. | |
| fact | When we spin and stop, the liquid keeps moving for a bit. The brain gets mixed-up messages and we feel dizzy. | |
| fact | Our eyes and feet help us balance too. | |
| answer | Your {object} helps you keep your balance. | |
| answer | Your ears have tiny tubes with a little liquid inside. After you stop spinning, it keeps moving, and you feel dizzy. | |
| answer | The liquid in your ears keeps moving after you stop. That mixes up your brain. | |

## 63. Thirst and water in the body (`thirst_water`)

Applies to: water, glass of water, water bottle, juice, milk, drink, soup, watermelon, cup of water, tea, cold water, smoothie

| Kind | Text | OK / fix |
|---|---|---|
| fact | Much of our body is water. | |
| fact | We lose water all day when we sweat, pee and breathe out. | |
| fact | When the body needs more water, it makes us feel thirsty. | |
| fact | Drinking water fills the body back up. | |
| answer | Your body needs water, and the {object} gives it some. | |
| answer | You lose water when you sweat and pee. Thirst tells you to drink more. | |
| answer | Much of your body is water. You must drink to keep it filled. | |

## 64. Gas bubbles in bread and fizzy drinks (`gas_bubbles`)

Applies to: bread dough, bread, bun, pizza dough, loaf, soda, fizzy drink, sparkling water, pancake, muffin, cake, cupcake, cola, roll, cinnamon roll

| Kind | Text | OK / fix |
|---|---|---|
| fact | Bread dough has yeast, a tiny living thing that eats sugar and makes bubbles of gas. | |
| fact | The bubbles puff the dough up, and baking makes it firm with holes inside. | |
| fact | Fizzy drinks have gas pushed into them. It bubbles out when you open the bottle. | |
| answer | Tiny bubbles of gas are inside the {object}. Those bubbles make it fizzy or fluffy. | |
| answer | Bread dough has yeast that makes gas bubbles. The bubbles make the dough big and fluffy. | |
| answer | Bread and fizzy drinks both have little bubbles of gas in them. | |

## 65. Rocks, sand and pebbles (`rocks_soil`)

Applies to: sand, pebble, beach, rock, river stone, boulder, mountain, gravel, cliff, desert sand, smooth stone

| Kind | Text | OK / fix |
|---|---|---|
| fact | Rocks come in many sizes, and some are hard and some are soft. | |
| fact | Wind, water and ice slowly wear big rocks into small stones, sand and soil. | |
| fact | This takes a very, very long time. | |
| fact | Soil has tiny rock bits and bits of dead leaves, so plants can grow in it. | |
| answer | In a long time, wind and water wear the {object} down. | |
| answer | Wind, water and ice slowly wear big rocks into sand. | |
| answer | Rocks rub together in rivers and waves. They become smooth and small. | |

## 66. Why the sea is salty (`ocean_water`)

Applies to: sea, ocean, seawater, sea water, ocean water, big sea, deep sea, blue sea, beach water, open sea

| Kind | Text | OK / fix |
|---|---|---|
| fact | Most of the water on Earth is in the sea. | |
| fact | Water flowing over rocks and soil picks up a little salt and carries it to the sea. | |
| fact | When sea water dries up, the salt stays behind. | |
| fact | We cannot drink seawater. Rivers and lakes have fresh water, which needs to be clean to drink. | |
| answer | Rivers carry a little salt from rocks to the sea. When sea water dries, the salt stays. | |
| answer | Rivers have carried salt to the {object} for a long time. | |
| answer | Sea water is too salty to drink. Rivers and lakes have fresh water. | |

## 67. Earthquakes (`earthquakes`)

Applies to: earthquake, quake, tremor, shaking ground, big earthquake, small earthquake, aftershock, ground shake, earth shaking, shaking floor

| Kind | Text | OK / fix |
|---|---|---|
| fact | The Earth's surface is made of huge pieces of rock that move very, very slowly. | |
| fact | When the rock pieces bump or slide, the ground shakes. That is an earthquake. | |
| fact | In an earthquake, get under a sturdy table and protect your head. | |
| answer | The {object} happens when rock under the ground moves. | |
| answer | Huge pieces of rock move very slowly. When they slip, the ground shakes. | |
| answer | In an earthquake, get under a table and cover your head. | |

## 68. Volcanoes (`volcanoes`)

Applies to: volcano, active volcano, volcano crater, volcano island, volcano mountain, erupting volcano, big volcano, tall volcano, sleeping volcano, volcano top

| Kind | Text | OK / fix |
|---|---|---|
| fact | Deep inside the Earth it is very hot, and some rock melts. | |
| fact | Hot melted rock pushes up and comes out of a volcano. We call it lava when it is outside. | |
| fact | Lava cools and turns back into hard rock. | |
| answer | Deep inside the Earth, rock is so hot that it melts. The {object} is where it comes out. | |
| answer | Hot melted rock pushes up and comes out of a volcano. Outside, it is called lava. | |
| answer | Lava cools and turns back into hard rock. | |

## 69. Fire and burning (`burning`)

Applies to: candle, match, campfire, fireplace, birthday candle, flame, bonfire, stove flame, fire pit, lighter flame, gas stove, wood fire, oil lamp, log fire, candle flame, barbecue fire

| Kind | Text | OK / fix |
|---|---|---|
| fact | A fire needs something to burn, air and heat. | |
| fact | Without air a fire goes out, like a candle under a glass. | |
| fact | Water can put a fire out. | |
| fact | Fire is hot and dangerous, so children must not play with it. | |
| answer | A fire needs something to burn, air and heat. The {object} needs air to keep burning. | |
| answer | Without air, a fire goes out. A glass over a candle makes the flame stop. | |
| answer | Fire is hot and dangerous. Children must never play with it. | |

## 70. Food going bad and fridges (`food_spoiling`)

Applies to: milk, bread, fruit, leftovers, cheese, rice, meat, yogurt, soup, fish, cut melon, lunch, sandwich, cake, tofu

| Kind | Text | OK / fix |
|---|---|---|
| fact | Food left for a long time grows germs and mold, and goes bad. | |
| fact | Germs grow faster when it is warm. | |
| fact | A fridge is cold, so germs grow slowly and food lasts longer. | |
| fact | Bad food can give us a tummy ache, so we must not eat it. | |
| answer | Germs and mold grow on the {object} if it sits out. | |
| answer | A fridge is cold, so germs grow slowly. Food lasts longer there. | |
| answer | Old food can give you a tummy ache. So we do not eat it. | |

## 71. How phones carry your voice (`phones_sound`)

Applies to: phone, mobile phone, cell phone, telephone, smartphone, landline, walkie-talkie, video call, tablet, phone call, toy phone, house phone

| Kind | Text | OK / fix |
|---|---|---|
| fact | A phone has a tiny microphone that turns your voice into a signal. | |
| fact | The signal travels far, through wires or through the air as invisible waves. | |
| fact | The other phone turns the signal back into sound, so your friend hears you. | |
| answer | A phone sends your talk far away as a message. | |
| answer | The other phone turns the message back into sound. Then your friend hears you. | |
| answer | The {object} sends your talk far away. | |
