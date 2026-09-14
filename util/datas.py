from datetime import datetime

def parsear_data(data_str: str) -> str:
    return datetime.fromisoformat(data_str).replace(
        second=0,
        microsecond=0
    )
