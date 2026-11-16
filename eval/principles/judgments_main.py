# AI judge (the experiment's author) verdicts for the answer produced after the UGen's own principle choice.
# verdict: right / partly / wrong ; F = contains a false (or nonsense) statement ; U = ungrounded (principle did not apply, model used own memory)
J = {
"zh-004": ("wrong", 1, 0), "zh-005": ("partly", 0, 0), "zh-007": ("wrong", 1, 0), "zh-009": ("right", 0, 0),
"zh-013": ("wrong", 1, 0), "zh-014": ("partly", 0, 0), "zh-015": ("wrong", 1, 0), "zh-023": ("partly", 0, 0),
"zh-026": ("wrong", 1, 0), "zh-028": ("wrong", 1, 0), "zh-034": ("wrong", 1, 0), "zh-035": ("wrong", 1, 0),
"zh-036": ("wrong", 1, 0), "zh-037": ("wrong", 0, 0), "zh-039": ("partly", 0, 0), "zh-040": ("right", 0, 0),
"zh-042": ("wrong", 1, 0), "zh-043": ("partly", 0, 0), "zh-044": ("wrong", 1, 0), "zh-048": ("right", 0, 1),
"zh-050": ("wrong", 0, 0),
"en-001": ("wrong", 1, 0), "en-002": ("partly", 1, 0), "en-003": ("wrong", 1, 0), "en-005": ("partly", 0, 1),
"en-010": ("wrong", 1, 0), "en-014": ("partly", 0, 0), "en-015": ("partly", 0, 0), "en-021": ("wrong", 1, 0),
"en-023": ("partly", 0, 0), "en-026": ("partly", 0, 1), "en-033": ("partly", 0, 0), "en-034": ("partly", 1, 0),
"en-035": ("wrong", 1, 0), "en-036": ("right", 0, 0), "en-037": ("partly", 0, 0), "en-039": ("right", 0, 0),
"en-040": ("right", 0, 0), "en-041": ("wrong", 1, 0), "en-042": ("wrong", 1, 0), "en-043": ("partly", 0, 0),
"en-044": ("wrong", 1, 0), "en-045": ("wrong", 1, 0), "en-046": ("partly", 1, 0), "en-048": ("right", 0, 1),
"en-049": ("right", 0, 0), "en-050": ("wrong", 0, 0),
"hz-02": ("wrong", 1, 0), "hz-03": ("right", 0, 0), "hz-04": ("wrong", 1, 0), "hz-05": ("wrong", 1, 0),
"hz-06": ("partly", 0, 0), "hz-08": ("right", 0, 0), "hz-09": ("wrong", 1, 0), "hz-10": ("partly", 0, 0),
"hz-11": ("wrong", 1, 0), "hz-12": ("partly", 1, 0), "hz-13": ("wrong", 1, 0), "hz-14": ("wrong", 1, 0),
"hz-15": ("partly", 1, 0), "hz-16": ("partly", 1, 0), "hz-17": ("wrong", 1, 0), "hz-18": ("wrong", 1, 0),
"hz-19": ("right", 0, 1), "hz-20": ("right", 0, 0),
"he-01": ("wrong", 1, 0), "he-02": ("partly", 0, 0), "he-04": ("partly", 0, 1), "he-05": ("wrong", 0, 0),
"he-06": ("wrong", 1, 0), "he-07": ("partly", 0, 0), "he-08": ("right", 0, 0), "he-09": ("partly", 0, 0),
"he-10": ("right", 0, 0), "he-11": ("right", 0, 0), "he-12": ("wrong", 1, 0), "he-13": ("wrong", 1, 0),
"he-14": ("wrong", 0, 0), "he-15": ("partly", 1, 0), "he-16": ("partly", 1, 0), "he-17": ("right", 0, 0),
"he-18": ("right", 0, 0), "he-19": ("right", 0, 1), "he-20": ("partly", 0, 0),
}

# Oracle run: answer step with the GOLD principle (only for gold full/partly questions where the UGen choice was not the gold principle).
O = {
"zh-002": ("wrong", 1), "zh-003": ("right", 0), "zh-007": ("partly", 0), "zh-014": ("partly", 0), "zh-021": ("wrong", 1),
"zh-023": ("right", 0), "zh-034": ("wrong", 1), "zh-035": ("wrong", 0), "zh-037": ("wrong", 1), "zh-041": ("partly", 0),
"zh-042": ("wrong", 1), "zh-043": ("right", 0), "zh-044": ("right", 0), "zh-046": ("right", 0), "zh-049": ("right", 0),
"en-003": ("right", 0), "en-014": ("partly", 0), "en-021": ("wrong", 1), "en-023": ("right", 0), "en-042": ("partly", 1),
"en-043": ("right", 0), "en-044": ("right", 0),
"hz-04": ("wrong", 1), "hz-05": ("wrong", 1), "hz-06": ("right", 0), "hz-07": ("wrong", 1), "hz-13": ("wrong", 1),
"hz-17": ("right", 0), "hz-18": ("partly", 0),
"he-02": ("partly", 0), "he-03": ("wrong", 1), "he-05": ("right", 0), "he-06": ("right", 0), "he-07": ("wrong", 1),
"he-14": ("wrong", 1), "he-16": ("partly", 0), "he-17": ("right", 0), "he-20": ("right", 0),
}
