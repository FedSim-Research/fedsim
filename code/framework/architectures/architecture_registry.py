
ARCHITECTURE_MAP = {
    "spyker": "SpykerArchitecture",
    "hierfl": "HierFLArchitecture",
}

def get_architecture(name: str):
    return ARCHITECTURE_MAP[name]