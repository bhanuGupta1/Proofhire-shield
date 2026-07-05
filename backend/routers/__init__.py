"""Feature routers mounted onto the main FastAPI app.

Each new platform surface area (candidates, jobs, pipeline, …) lives in its own
module here rather than growing main.py. main.py imports and `include_router`s
them. Every router reuses the shared auth + db dependencies and the same
tenant-scoping rule as the core scan endpoints.
"""
