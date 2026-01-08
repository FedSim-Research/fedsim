from queue import PriorityQueue


class SimulationOrchestrator:
    event_queue = PriorityQueue()  # Use: event_queue.put((event.trigger_time, event))
