import re
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class ParsedClip:
    clip_type: str       # "BASE", "B-ROLL", or "DEFAULT" (for backwards compatibility)
    start_str: str       # e.g., "0_0"
    end_str: str         # e.g., "4_71"
    start_sec: float     # e.g., 0.0
    end_sec: float       # e.g., 4.71
    duration: float      # e.g., 4.71
    content: str         # The prompt text or filename suffix

    @property
    def expected_filename(self) -> str:
        """Standardizes the filename for Scrapers and Assemblers."""
        return f"[{self.clip_type}]_{self.start_str}-{self.end_str}_image.png"

class TimelineParser:
    # Matches: [BASE] [0_0-4_71] Prompt... OR [0_0-4_71] Prompt...
    PROMPT_PATTERN = re.compile(r"^(?:\[([A-Z-]+)\]\s*)?\[\s*([\d_]+)\s*-\s*([\d_]+)\s*\]\s*(.*)")
    
    # Matches: [BASE]_[0_0-4_71]_image.png OR [0_0-4_71]_image.png
    FILENAME_PATTERN = re.compile(r"^(?:\[([A-Z-]+)\]_)?\[([\d_]+)-([\d_]+)\].*")

    @staticmethod
    def _time_to_sec(time_str: str) -> float:
        try:
            return float(time_str.replace('_', '.'))
        except ValueError:
            return 0.0

    @classmethod
    def parse_prompt_line(cls, line: str) -> Optional[ParsedClip]:
        """Extracts data from time_stamped_prompts.txt lines."""
        match = cls.PROMPT_PATTERN.match(line.strip())
        if not match:
            return None
            
        clip_type = match.group(1) or "DEFAULT"
        start_str = match.group(2)
        end_str = match.group(3)
        content = match.group(4)
        
        start_sec = cls._time_to_sec(start_str)
        end_sec = cls._time_to_sec(end_str)
        
        return ParsedClip(
            clip_type=clip_type,
            start_str=start_str,
            end_str=end_str,
            start_sec=start_sec,
            end_sec=end_sec,
            duration=max(0.0, round(end_sec - start_sec, 3)),
            content=content
        )

    @classmethod
    def parse_filename(cls, filename: str) -> Optional[ParsedClip]:
        """Extracts data from media filenames."""
        match = cls.FILENAME_PATTERN.match(filename.strip())
        if not match:
            return None
            
        clip_type = match.group(1) or "DEFAULT"
        start_str = match.group(2)
        end_str = match.group(3)
        
        start_sec = cls._time_to_sec(start_str)
        end_sec = cls._time_to_sec(end_str)
        
        return ParsedClip(
            clip_type=clip_type,
            start_str=start_str,
            end_str=end_str,
            start_sec=start_sec,
            end_sec=end_sec,
            duration=max(0.0, round(end_sec - start_sec, 3)),
            content=filename
        )