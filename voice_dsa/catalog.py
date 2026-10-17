"""Study catalog for the Learn and Quiz pages. Add a subject or topic here and it appears everywhere."""

SUBJECTS = {
    "dsa": {
        "title": "Data Structures & Algorithms", "icon": "🧩",
        "topics": ["Arrays & Hashing", "Two Pointers", "Sliding Window", "Stacks & Queues", "Linked Lists", "Trees & BSTs",
                   "Graphs (BFS, DFS, Topological Sort)", "Heaps & Priority Queues", "Binary Search", "Dynamic Programming",
                   "Backtracking", "Greedy & Intervals", "Bit Manipulation", "Time & Space Complexity"],
    },
    "system_design": {
        "title": "System Design", "icon": "🏗️",
        "topics": ["Scalability Basics", "Load Balancing", "Caching Strategies", "Database Sharding & Replication",
                   "Consistent Hashing", "Message Queues & Event Streaming", "CAP Theorem & Consistency Models",
                   "API Design & Rate Limiting", "Design a URL Shortener", "Design a Chat System"],
    },
    "oop": {
        "title": "OOP & Low-Level Design", "icon": "🧱",
        "topics": ["Four Pillars of OOP", "SOLID Principles", "Creational Design Patterns", "Behavioral Design Patterns",
                   "Design a Parking Lot", "Composition vs Inheritance"],
    },
    "dbms": {
        "title": "Databases & SQL", "icon": "🗄️",
        "topics": ["SQL Joins", "Indexing & B-Trees", "Transactions & ACID", "Normalization", "Isolation Levels & Locking",
                   "Query Optimization"],
    },
    "os": {
        "title": "Operating Systems", "icon": "⚙️",
        "topics": ["Processes vs Threads", "CPU Scheduling", "Deadlocks", "Memory Management & Paging",
                   "Synchronization (Mutex, Semaphore)", "File Systems"],
    },
    "networks": {
        "title": "Computer Networks", "icon": "🌐",
        "topics": ["OSI & TCP/IP Models", "TCP vs UDP", "HTTP, HTTPS & TLS", "DNS", "REST vs gRPC vs WebSockets",
                   "What Happens When You Type a URL"],
    },
    "behavioral": {
        "title": "Behavioral & HR", "icon": "🤝",
        "topics": ["The STAR Method", "Handling Conflict & Feedback", "Leadership & Ownership", "Failure & Learning",
                   "Tell Me About Yourself", "Why This Company?"],
    },
}


def valid(subject: str, topic: str) -> bool:
    return subject in SUBJECTS and topic in SUBJECTS[subject]["topics"]


def public() -> list:
    return [{"id": k, "title": v["title"], "icon": v["icon"], "topics": v["topics"]} for k, v in SUBJECTS.items()]
