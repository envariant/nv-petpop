# petpop_style LoRA (S4)

1. Build the hand-made base meshes (Section 10), then render the set:
   `python assets/lora/make_training_set.py --count 150` (Cycles; on the GPU box use CUDA).
2. Add the licensed/original reference figurine images with captions starting `petpop_style,`.
3. Train with Kohya sd-scripts: `accelerate launch sdxl_train_network.py --config_file assets/lora/kohya_petpop_style.toml`.
4. Gate: side-by-side with and without the LoRA on 10 prompts; pin the output in `pipelines/comfy/models.yaml`.
