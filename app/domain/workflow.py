from typing import List, Dict, Tuple

class WorkflowEngine:
    @staticmethod
    def validate_transition(
        current_status_id: str,
        target_status_id: str,
        allowed_transitions: List[Tuple[str, str]]  # List of (from_status_id, to_status_id)
    ) -> Tuple[bool, List[str]]:
        """
        Validates if an issue status transition is permitted.
        Returns:
            A tuple of (is_valid: bool, allowed_target_status_ids: List[str])
        """

        valid_targets = [to_id for from_id, to_id in allowed_transitions if from_id == current_status_id]
        
        if target_status_id in valid_targets:
            return True, valid_targets
            
        return False, valid_targets