import os
import json
import time
from pathlib import Path
from app.models.script_schema import ReviewResponse

SLEEP_TIME = 25

class ScriptGenerationService:
    """
    Manages the Directed AI agentic loop for writing high-quality scripts with State Machine Checkpointing.
    """
    def __init__(self, llm_client, prompt_dir: Path, output_dir: Path = None):
        self.llm = llm_client
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.prompt_dir = prompt_dir 
        
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_path = self.output_dir / "script_generation.log"
        self.checkpoint_path = self.output_dir / "script_checkpoint.json"

    def _read_prompt(self, filename: str) -> str:
        path = self.prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"[!] Critical Error: Prompt document '{filename}' is missing from {self.prompt_dir}.")
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
        
        # Checkpoint is now preserved on the hard drive for debugging/records!

    def _save_checkpoint(self, state: dict):
        """Persists the exact state of the agentic loop."""
        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)

    def generate_script(self, title: str, core_theme: str, target_minutes: int = 4, max_retries: int = 3) -> str:
        print(f"\n[Brain] Starting Directed AI pipeline for: '{title}'")
        print(f"[Brain] Core Theme: '{core_theme}'")
        
        target_words_min = (target_minutes - 1) * 150
        target_words_max = target_minutes * 150
        
        # --- STATE MACHINE INITIALIZATION ---
        state = {
            "phase": "drafting", # phases: drafting, evaluating, editing
            "iteration": 1,
            "current_script": "",
            "best_script": "",
            "best_score": 0.0,
            "review_history": [],
            "last_review_data": None # Stores the review so the Editor can resume if interrupted
        }
        
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            print(f"[Checkpoint] Resuming Brain Loop at Iteration {state['iteration']}, Phase: {state['phase'].upper()}")
        else:
            self._save_log(f"TITLE: {title}\nCORE THEME: {core_theme}\nTARGET LENGTH: {target_minutes} mins\n", append=False)

        instructions = self._read_prompt("script_instructions.txt")
        
        # ==========================================
        # PHASE 1: DRAFTING
        # ==========================================
        if state["phase"] == "drafting":
            system_prompt = (
                f"Title: {title}\n"
                f"Core Theme: {core_theme}\n"
                f"Length Constraint: Write between {target_words_min} and {target_words_max} words.\n\n"
                f"Instructions:\n{instructions}"
            )
            
            print("\n[Pipeline] Generating initial draft...")
            current_script = self.llm.generate_text(system_prompt)
            self._save_log(f"--- DRAFT 0 (Initial) ---\n\n{current_script}")
            
            # Update State
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
                reviewer_instructions = self._read_prompt("script_reviewer.txt")
                review_prompt = f"Script to review:\n{state['current_script']}\n\nInstructions:\n{reviewer_instructions}"
                
                review_result_raw = self.llm.generate_json(review_prompt, response_model=ReviewResponse)
                review_dict = json.loads(review_result_raw)
                review_data = ReviewResponse(**review_dict)
                
                print(f"  [Evaluator] Score: {review_data.score}/10.0 | Publish: {review_data.publish}")
                self._save_log(f"--- REVIEW {state['iteration']} (Score: {review_data.score}) ---\n\n{json.dumps(review_dict, indent=2)}")
                
                # Check High-Water Mark
                if review_data.score > state["best_score"]:
                    state["best_score"] = review_data.score
                    state["best_script"] = state["current_script"]
                    print(f"  -> New High-Water Mark! (Score: {state['best_score']})")
                
                # Save review data so the editor can use it, even if the script crashes right now
                state["last_review_data"] = review_dict
                state["phase"] = "editing"
                self._save_checkpoint(state)
                
                # Check Completion (FORCED EDIT LOCK IMPLEMENTED)
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
                editor_instructions = self._read_prompt("script_editor.txt")
                
                # Rebuild Pydantic object from checkpoint dictionary
                r_data = ReviewResponse(**state["last_review_data"])
                
                editor_prompt = (
                    f"Original Script:\n{state['current_script']}\n\n"
                    f"Core Theme: {core_theme}\n"
                    f"--- EDITING PROJECT PLAN ---\n"
                    f"Strategy: {r_data.editor_strategy}\n"
                    f"Retention Heatmap: {json.dumps([rm.model_dump() for rm in r_data.retention_map], indent=2)}\n"
                    f"Critical Tasks (Must Fix): {json.dumps(r_data.must_fix, indent=2)}\n"
                    f"Minor Tasks (Should Fix): {json.dumps(r_data.should_fix, indent=2)}\n"
                    f"DO NOT TOUCH (Preserve): {json.dumps(r_data.preserve, indent=2)}\n\n"
                    f"--- PREVIOUS ITERATION FEEDBACK ---\n"
                    f"{json.dumps(state['review_history'], indent=2)}\n\n"
                    f"Length Constraint: The final rewritten script MUST be between {target_words_min} and {target_words_max} words.\n\n"
                    f"Instructions:\n{editor_instructions}"
                )
                
                # Add current review to history for the NEXT loop
                state["review_history"].append(state["last_review_data"])
                
                new_script = self.llm.generate_text(editor_prompt)
                self._save_log(f"--- EDITED DRAFT {state['iteration']} ---\n\n{new_script}")
                
                # Reset state for the next evaluation pass
                state["current_script"] = new_script
                state["iteration"] += 1
                state["phase"] = "evaluating"
                state["last_review_data"] = None
                self._save_checkpoint(state)
                
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits...")
                time.sleep(SLEEP_TIME)
                
        # ==========================================
        # FALLBACK: MAX RETRIES REACHED
        # ==========================================
        print(f"\n[Brain] Max retries reached. Saving the BEST available script from the high-water mark tracker (Score: {state['best_score']}).")
        self._save_final_script(state["best_script"])
        return state["best_script"]