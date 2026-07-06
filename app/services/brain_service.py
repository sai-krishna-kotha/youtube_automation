import os
import json
import time
from pathlib import Path
from app.models.script_schema import ReviewResponse
SLEEP_TIME = 5

class ScriptGenerationService:
    """
    Manages the Directed AI agentic loop for writing high-quality scripts.
    """
    def __init__(self, llm_client, prompt_dir: Path, output_dir: Path = None):
        """
        Initializes the service with LLM client, prompt docs directory, and dynamic output directory.
        """
        self.llm = llm_client
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.prompt_dir = prompt_dir # Dynamics injection for multi-channel support
        
        # Use provided run-specific directory, or fallback to default for debugging
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Internal log file to trace the state of iterations
        self.log_path = self.output_dir / "script_generation.log"

    def _read_prompt(self, filename: str) -> str:
        """Reads the content of a specific prompt doc file."""
        path = self.prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"[!] Critical Error: Prompt document '{filename}' is missing from {self.prompt_dir}.")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _save_log(self, text: str, append: bool = True):
        """Saves current state information to a local log file."""
        mode = 'a' if append else 'w'
        with open(self.log_path, mode, encoding='utf-8') as f:
            f.write(text + "\n" + "="*50 + "\n\n")

    def _save_final_script(self, script_text: str):
        """Saves the final accepted script to a text file for the next module."""
        path = self.output_dir / "final_script.txt"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(script_text)
        print(f"[Brain] Final script saved to: {path}")

    def generate_script(self, title: str, core_theme: str, target_minutes: int = 4, max_retries: int = 3) -> str:
        print(f"\n[Brain] Starting Directed AI pipeline for: '{title}'")
        print(f"[Brain] Core Theme: '{core_theme}'")
        
        target_words_min = (target_minutes - 1) * 150
        target_words_max = target_minutes * 150
        
        self._save_log(f"TITLE: {title}\nCORE THEME: {core_theme}\nTARGET LENGTH: {target_minutes} mins\n", append=False)

        instructions = self._read_prompt("script_instructions.txt")
        system_prompt = (
            f"Title: {title}\n"
            f"Core Theme: {core_theme}\n"
            f"Length Constraint: Write between {target_words_min} and {target_words_max} words.\n\n"
            f"Instructions:\n{instructions}"
        )
        
        current_script = self.llm.generate_text(system_prompt)
        print("\n[Pipeline] First draft generated. Sending to Audience Advocate Evaluator...")
        self._save_log(f"--- DRAFT 0 (Initial) ---\n\n{current_script}")
        
        best_script = current_script
        best_score = 0.0
        
        # --- NEW: THE REVIEW HISTORY LOOP ---
        review_history = [] 
        
        iteration = 0
        while iteration < max_retries:
            iteration += 1
            print(f"\n--- Script Iteration {iteration} ---")
            time.sleep(SLEEP_TIME)
            
            print("  [Evaluator] Assessing script and generating Editing Project Plan...")
            reviewer_instructions = self._read_prompt("script_reviewer.txt")
            review_prompt = f"Script to review:\n{current_script}\n\nInstructions:\n{reviewer_instructions}"
            
            review_result_raw = self.llm.generate_json(review_prompt, response_model=ReviewResponse)
            review_data = ReviewResponse(**json.loads(review_result_raw))
            # print(f"Review DATA: {review_data}")
            print(f"  [Evaluator] Score: {review_data.score}/10.0 | Publish: {review_data.publish}")
            self._save_log(f"--- REVIEW {iteration} (Score: {review_data.score}) ---\n\n{json.dumps(review_data.model_dump(), indent=2)}")
            
            if review_data.score > best_score:
                best_score = review_data.score
                best_script = current_script
                print(f"  -> New High-Water Mark! (Score: {best_score})")
            
            # We now respect the Reviewer's absolute 'publish' boolean alongside the score
            if review_data.publish or review_data.score >= 9.5:
                print("\n[Pipeline] Evaluator approved publication. Saving final script.")
                self._save_final_script(best_script)
                return best_script
                
            if iteration == max_retries:
                print("  [Pipeline] Final iteration reached without approval. Halting edits.")
                break
            
            print("  [Editor] Executing the Project Plan tasks...")
            time.sleep(SLEEP_TIME)
            
            editor_instructions = self._read_prompt("script_editor.txt")
            
            # --- NEW: STRUCTURED EDITOR PROMPT ---
            editor_prompt = (
                f"Original Script:\n{current_script}\n\n"
                f"Core Theme: {core_theme}\n"
                f"--- EDITING PROJECT PLAN ---\n"
                f"Strategy: {review_data.editor_strategy}\n"
                f"Retention Heatmap: {json.dumps([rm.model_dump() for rm in review_data.retention_map], indent=2)}\n"
                f"Critical Tasks (Must Fix): {json.dumps(review_data.must_fix, indent=2)}\n"
                f"Minor Tasks (Should Fix): {json.dumps(review_data.should_fix, indent=2)}\n"
                f"DO NOT TOUCH (Preserve): {json.dumps(review_data.preserve, indent=2)}\n\n"
                f"--- PREVIOUS ITERATION FEEDBACK (Do not repeat past mistakes) ---\n"
                f"{json.dumps(review_history, indent=2)}\n\n"
                f"Length Constraint: The final rewritten script MUST be between {target_words_min} and {target_words_max} words.\n\n"
                f"Instructions:\n{editor_instructions}"
            )
            
            # Log the current review to history AFTER building the prompt (so we don't feed it its own immediate review in the history block)
            review_history.append(review_data.model_dump())
            
            current_script = self.llm.generate_text(editor_prompt)
            self._save_log(f"--- EDITED DRAFT {iteration} ---\n\n{current_script}")
            
        print(f"\n[Brain] Max retries reached. Saving the BEST available script from the high-water mark tracker (Score: {best_score}).")
        self._save_final_script(best_script)
        return best_script