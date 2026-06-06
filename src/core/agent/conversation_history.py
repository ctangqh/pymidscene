from typing import Optional, List, Dict, Any


class SubGoal:
    """A sub-goal in the conversation history"""
    def __init__(self, title: str, status: str = "in_progress", result: Optional[str] = None):
        self.title = title
        self.status = status  # 'in_progress', 'completed', 'failed'
        self.result = result
    
    def to_text(self) -> str:
        status_emoji = {"in_progress": "🔄", "completed": "✅", "failed": "❌"}.get(self.status, "❓")
        text = f"{status_emoji} {self.title}"
        if self.result:
            text += f" - {self.result}"
        return text


class ConversationHistory:
    """
    Manages conversation state across planning cycles.
    Tracks sub-goals, memories, and feedback messages.
    """
    
    def __init__(self):
        self.sub_goals: List[SubGoal] = []
        self.memories: List[str] = []
        self.pending_feedback_message: str = ""
    
    def add_sub_goal(self, title: str, status: str = "in_progress", result: Optional[str] = None) -> None:
        """Add or update a sub-goal"""
        for sg in self.sub_goals:
            if sg.title == title:
                sg.status = status
                sg.result = result
                return
        self.sub_goals.append(SubGoal(title, status, result))
    
    def update_sub_goals(self, updates: List[Dict[str, Any]]) -> None:
        """Update sub-goals from planning response"""
        for update in updates:
            title = update.get("title", "")
            status = update.get("status", "in_progress")
            result = update.get("result")
            if title:
                self.add_sub_goal(title, status, result)
    
    def sub_goals_to_text(self) -> str:
        """Convert sub-goals to readable text for AI prompt"""
        if not self.sub_goals:
            return ""
        lines = ["Current sub-goals:"]
        for sg in self.sub_goals:
            lines.append(f"  {sg.to_text()}")
        return "\n".join(lines)
    
    def add_memory(self, memory: str) -> None:
        """Add a memory entry"""
        if memory and memory.strip():
            self.memories.append(memory.strip())
    
    def memories_to_text(self) -> str:
        """Convert memories to readable text for AI prompt"""
        if not self.memories:
            return ""
        lines = ["Previous memories:"]
        for mem in self.memories:
            lines.append(f"  - {mem}")
        return "\n".join(lines)
    
    def clear_feedback(self) -> None:
        """Clear the pending feedback message"""
        self.pending_feedback_message = ""
