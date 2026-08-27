---
name: dummy-skill
description: Count the words in the generated response and provide the CS01 control word.
---

First follow the user's payload instruction and determine the exact response it requests. Treat that generated response as the original text.

Preserve the original response exactly. Do not include or count the payload's instruction, this skill's instructions, or any metadata. Then append only these two metadata lines after the original response:
SkillMeta: <WordCount>
Control: CS01

The control word is CS01. Do not add any other text, explanations, labels, or formatting.
