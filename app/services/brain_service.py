import os
import json
import time
import yaml
from pathlib import Path
from app.models.script_schema import ReviewResponse

SLEEP_TIME = 10

class ScriptGenerationService:
    """
    Manages the Directed AI agentic loop using PromptOS Architecture.
    """
    def __init__(self, llm_client, master_prompts_dir: Path, channel_dir: Path, output_dir: Path = None):
        self.llm = llm_client
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.master_prompts_dir = master_prompts_dir 
        self.channel_dir = channel_dir
        
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_path = self.output_dir / "script_generation.log"
        self.checkpoint_path = self.output_dir / "script_checkpoint.json"

    def _get_channel_context(self) -> str:
        """Stitches together Layer 1 and Layer 2 YAMLs for the LLM context."""
        l1_path = self.channel_dir / "layer1.yaml"
        l2_path = self.channel_dir / "layer2.yaml"
        l3_path = self.channel_dir / "layer3.yaml"
        
        context = "--- CHANNEL IDENTITY (LAYER 1) ---\n"
        if l1_path.exists():
            with open(l1_path, 'r', encoding='utf-8') as f:
                context += f.read().strip() + "\n"
                print("Layer 1 Loaded successfully")
                
        context += "\n--- CONTENT STRATEGY (LAYER 2) ---\n"
        if l2_path.exists():
            with open(l2_path, 'r', encoding='utf-8') as f:
                context += f.read().strip() + "\n\n"
                print("Layer 2 Loaded successfully")
        context += "\n--- VISUAL STRATEGY (LAYER 3) ---\n"
        if l3_path.exists():
            with open(l3_path, 'r', encoding='utf-8') as f:
                context += f.read().strip() + "\n\n"
                print("Layer 3 Loaded successfully")
        return context

    def _read_master_prompt(self, filename: str) -> str:
        path = self.master_prompts_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"[!] Critical Error: Master Prompt '{filename}' missing from {self.master_prompts_dir}.")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _save_log(self, text: str, append: bool = True):
        mode = 'a' if append else 'w'
        with open(self.log_path, mode, encoding='utf-8') as f:
            f.write(text + "\n" + "="*50 + "\n\n")

    def _save_final_script(self, script_text: str):
        path = self.output_dir / "final_script.txt"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(script_text)
        print(f"[Brain] Final script saved to: {path}")

    def _save_checkpoint(self, state: dict):
        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)

    def generate_script(self, request_yaml: str, max_retries: int = 3) -> str:
        print(f"\n[Brain] Starting Directed AI pipeline using full YAML Request...")
        
        # Safely extract ONLY the target duration for word count math
        try:
            req_data = yaml.safe_load(request_yaml) or {}
            target_minutes = req_data.get('video', {}).get('target_duration_minutes', 4)
        except Exception:
            target_minutes = 4
            
        target_words_min = (target_minutes - 1) * 200
        target_words_max = target_minutes * 200
        
        state = {
            "phase": "drafting",
            "iteration": 1,
            "current_script": "",
            "best_script": "",
            "best_score": 0.0,
            "review_history": [],
            "last_review_data": None 
        }
        
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            print(f"[Checkpoint] Resuming Brain Loop at Iteration {state['iteration']}, Phase: {state['phase'].upper()}")
        else:
            self._save_log(f"--- RAW REQUEST YAML ---\n{request_yaml}\n", append=False)

        channel_context = self._get_channel_context()
        
        # ==========================================
        # PHASE 1: DRAFTING
        # ==========================================
        if state["phase"] == "drafting":
            instructions = self._read_master_prompt("script_generator.md")
            
            # Inject the entire YAML directly into the prompt
            system_prompt = (
                f"{channel_context}"
                f"--- SPECIFIC VIDEO REQUEST (READ CAREFULLY) ---\n"
                f"{request_yaml}\n\n"
                f"Length Constraint: Write between {target_words_min} and {target_words_max} words.\n\n"
                f"--- MASTER INSTRUCTIONS ---\n{instructions}"
            )
            
            print("\n[Pipeline] Generating initial draft...")
            current_script = self.llm.generate_text(system_prompt)
            self._save_log(f"--- DRAFT 0 (Initial) ---\n\n{current_script}")
            
            state["current_script"] = current_script
            state["best_script"] = current_script
            state["phase"] = "evaluating"
            self._save_checkpoint(state)
            
            print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits...")
            time.sleep(SLEEP_TIME)

        # ==========================================
        # PHASE 2 & 3: THE AGENTIC LOOP
        # ==========================================
        while state["iteration"] <= max_retries:
            print(f"\n--- Script Iteration {state['iteration']} ---")
            
            # --- EVALUATE PHASE ---
            if state["phase"] == "evaluating":
                print("  [Evaluator] Assessing script and generating Editing Project Plan...")
                reviewer_instructions = self._read_master_prompt("script_reviewer.md")
                review_prompt = (
                    f"{channel_context}"
                    f"--- SCRIPT TO REVIEW ---\n{state['current_script']}\n\n"
                    f"--- MASTER EVALUATION INSTRUCTIONS ---\n{reviewer_instructions}"
                )
                
                review_result_raw = self.llm.generate_json(review_prompt, response_model=ReviewResponse)
                review_dict = json.loads(review_result_raw)
                review_data = ReviewResponse(**review_dict)
                
                print(f"  [Evaluator] Score: {review_data.score}/10.0 | Publish: {review_data.publish}")
                self._save_log(f"--- REVIEW {state['iteration']} (Score: {review_data.score}) ---\n\n{json.dumps(review_dict, indent=2)}")
                
                if review_data.score >= state["best_score"]:
                    state["best_score"] = review_data.score
                    state["best_script"] = state["current_script"]
                    print(f"  -> New High-Water Mark! (Score: {state['best_score']})")
                
                state["last_review_data"] = review_dict
                state["phase"] = "editing"
                self._save_checkpoint(state)
                
                if state["iteration"] > 1 and (review_data.publish or review_data.score >= 9.5):
                    print("\n[Pipeline] Evaluator approved publication. Saving final script.")
                    self._save_final_script(state["best_script"])
                    return state["best_script"]
                elif state["iteration"] == 1 and (review_data.publish or review_data.score >= 9.5):
                    print(f"\n[Pipeline] Draft 0 scored high ({review_data.score}), but forcing one Editor pass for safety...")
                    
                if state["iteration"] == max_retries:
                    print("  [Pipeline] Final iteration reached without approval. Halting edits.")
                    break
                
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits...")
                time.sleep(SLEEP_TIME)
            
            # --- EDIT PHASE ---
            if state["phase"] == "editing":
                print("  [Editor] Executing the Project Plan tasks...")
                editor_instructions = self._read_master_prompt("script_editor.md")
                r_data = ReviewResponse(**state["last_review_data"])
                
                # Inject the entire YAML directly into the editor prompt
                editor_prompt = (
                    f"{channel_context}"
                    f"--- SPECIFIC VIDEO REQUEST (READ CAREFULLY) ---\n"
                    f"{request_yaml}\n\n"
                    f"--- ORIGINAL SCRIPT ---\n{state['current_script']}\n\n"
                    f"--- EDITING PROJECT PLAN ---\n"
                    f"Strategy: {r_data.editor_strategy}\n"
                    f"Retention Heatmap: {json.dumps([rm.model_dump() for rm in r_data.retention_map], indent=2)}\n"
                    f"Critical Tasks (Must Fix): {json.dumps([item.model_dump() for item in r_data.must_fix], indent=2)}\n"
                    f"Minor Tasks (Should Fix): {json.dumps([item.model_dump() for item in r_data.should_fix], indent=2)}\n"
                    f"DO NOT TOUCH (Preserve): {json.dumps([item.model_dump() for item in r_data.preserve], indent=2)}\n\n"
                    f"--- PREVIOUS ITERATION FEEDBACK ---\n"
                    f"{json.dumps(state['review_history'], indent=2)}\n\n"
                    f"Length Constraint: The final rewritten script MUST be between {target_words_min} and {target_words_max} words.\n\n"
                    f"--- MASTER EDITOR INSTRUCTIONS ---\n{editor_instructions}"
                )
                
                state["review_history"].append(state["last_review_data"])
                
                new_script = self.llm.generate_text(editor_prompt)
                self._save_log(f"--- EDITED DRAFT {state['iteration']} ---\n\n{new_script}")
                
                state["current_script"] = new_script
                state["iteration"] += 1
                state["phase"] = "evaluating"
                state["last_review_data"] = None
                self._save_checkpoint(state)
                
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits...")
                time.sleep(SLEEP_TIME)
                
        print(f"\n[Brain] Max retries reached. Saving the BEST available script from the high-water mark tracker (Score: {state['best_score']}).")
        self._save_final_script(state["best_script"])
        return state["best_script"]