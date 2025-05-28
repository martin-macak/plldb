from typing import Dict


class Debugger:
    def __init__(self):
        pass

    def handle_message(self, message: Dict):
        pass

    
class InvalidMessageError(Exception):
    pass