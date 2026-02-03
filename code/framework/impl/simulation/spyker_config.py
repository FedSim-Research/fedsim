from dataclasses import dataclass

@dataclass
class SpykerConfig:
    # --- Algorithm 1: Client Learning Rate Decay ---
    decay_beta: float = 0.05
    min_learning_rate: float = 1e-6
    
    # --- Algorithm 2: Server Synchronization Triggers ---
    # Max allowed age difference between any two servers
    h_inter: int = 5         
    # Max allowed age difference on local server since last sync
    h_intra: int = 350       
    
    # --- Server Aggregation ---
    # Controls the steepness of the sigmoid function for model weighting
    sigmoid_phi: float = 1.5 
    # Learning rate for merging server models (eta_a)
    server_learning_rate: float = 0.6
    
    # --- TCP Simulation ---
    # Estimated time to detect a lost packet and resend (RTO) in seconds
    tcp_rto_delay: float = 0.2
