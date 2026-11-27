# Handoff check: LLMClient + Run 1 adapter vs our evaluation

Question: does the backend produce the same answers as our evaluation notebook for the Run 1 adapter?

## Setup (must be identical on both sides)
- Base model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`, bf16 (NOT the unsloth 4-bit copy used for training)
- Adapter: `finetuning/adapters/` loaded with `PeftModel.from_pretrained(base, adapter_path)`
- Prompt formatting: `tokenizer.apply_chat_template(messages, add_generation_prompt=True)`, same system message as the evaluation (write it here: ___)
- Greedy decoding (`do_sample=False`), `max_new_tokens=512`, batch size 1
- Hardware: Kaggle T4. Library versions recorded in the output file.

## Prompts (10)
P1, P2, P7, P9, P10, P13, P14, HumanEval/0, HumanEval/6, V2

## Reference answers
Taken from the Run 1 result files of our own evaluation (no new generation).

## Pass rule (written before running)
- PASS if at least 8 of 10 answers are identical after whitespace normalization AND every difference is explained.
- Otherwise FAIL: do not build on the adapter until the cause is found.

## Result
(to fill after the run: date, who ran it, versions, X/10 identical, explanation of differences)