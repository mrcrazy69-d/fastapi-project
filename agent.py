from langchain.agents import Tool, initialize_agent
from langchain.llms import GPT4All
from requests.auth import HTTPBasicAuth
import requests
import json
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ─── Local LLM ─────────────────────────────────────────────────────────────
llm = GPT4All(
    model="mistral-7b-openorca.Q4_0.gguf",
    allow_download=False,
    backend="gptj",
    verbose=False,
    max_tokens=200
)

BASE = "http://127.0.0.1:8000"
AUTH = HTTPBasicAuth("admin", "pass123")

# ─── Helper Functions ──────────────────────────────────────────────────────
def get_all_tasks_by_user(query: str):
    try:
        query = query.strip().lower()
        user_id = None

        if query.isdigit():
            user_id = query
        else:
            users = requests.get(f"{BASE}/users", auth=AUTH, timeout=7).json()
            for u in users:
                if query in u['name'].lower():
                    user_id = u['id']
                    break

        if not user_id:
            return f"❌ No user found matching '{query}'. Try using full name or ID."

        url = f"{BASE}/tasks?user_id={user_id}"
        r = requests.get(url, auth=AUTH, timeout=5)
        tasks = r.json()
        if not tasks:
            return f"🟡 No tasks found for user ID {user_id}."
        return "\n".join([f"- {t['title']} (status: {t['status']})" for t in tasks])
    except Exception as e:
        return f"⚠️ Error: {e}"


def get_all_users(_):
    try:
        r = requests.get(f"{BASE}/users", auth=AUTH, timeout=7)
        users = r.json()
        if not users:
            return "No users found."
        return "\n".join([f"- {u['name']} (ID: {u['id']}, Email: {u['email']})" for u in users])
    except Exception as e:
        return f"⚠️ Couldn't fetch users: {e}"

def get_tasks_by_status(status: str):
    try:
        clean_status = status.strip().lower().replace("'", "")
        r = requests.get(f"{BASE}/tasks?status={clean_status}", timeout=5)
        tasks = r.json()
        if not tasks:
            return f"No tasks with status '{clean_status}'."
        return "\n".join([f"- {t['title']} (User ID: {t['user_id']})" for t in tasks])
    except Exception as e:
        return f"⚠️ Couldn't fetch tasks: {e}"

def get_pending_tasks_by_user(query: str):
    try:
        # Extract just the digits or a clean string
        clean_input = query.strip().lower()
        match = re.match(r"^\D*(\d+)\D*$", clean_input)  # pull numeric ID

        user_id = None

        if match:
            user_id = match.group(1)  # it's a number string like "3"
        else:
            # fallback to name match
            users = requests.get(f"{BASE}/users", auth=AUTH, timeout=7).json()
            for u in users:
                if clean_input in u['name'].lower():
                    user_id = u['id']
                    break

        if not user_id:
            return f"❌ No user found matching '{query}'. Try using a valid ID or full name."

        url = f"{BASE}/tasks/pending?user_id={user_id}"
        r = requests.get(url, auth=AUTH, timeout=5)
        tasks = r.json()

        if isinstance(tasks, list) and tasks:
            return "\n".join([f"- {t['title']} (status: {t['status']})" for t in tasks])
        return f"🟡 No pending tasks found for user ID {user_id}."

    except Exception as e:
        return f"⚠️ Error fetching pending tasks: {e}"



# ─── LangChain Tools ───────────────────────────────────────────────────────
tools = [
    Tool(
        name="UserAPI_GetAll",
        func=get_all_users,
        description="Use this to list all users in the system. Best used when the question is about users or listing user names, IDs, or emails.",
        return_direct=True
    ),
    Tool(
        name="TaskAPI_GetByStatus",
        func=get_tasks_by_status,
        description="Use this to find tasks by their status, like 'pending' or 'completed'."
    ),
    Tool(
        name="PendingTasks_ByUser",
        func=get_pending_tasks_by_user,
        description="Use this to find all PENDING tasks for a specific user, by name or ID.",
        return_direct=True
    ),
    Tool(
        name="AllTasks_ByUser",
        func=get_all_tasks_by_user,
        description="Use this to list ALL tasks for a specific user, by name or ID.",
        return_direct=True
    )
]

# ─── LangChain Agent Executor ───────────────────────────────────────────────
from langchain.agents import initialize_agent

agent_executor = initialize_agent(
    tools=tools,
    llm=llm,
    agent_type="zero-shot-react-description",
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=3,
    early_stopping_method="generate",
    return_intermediate_steps=True
)

# ─── Smart Wrapper ──────────────────────────────────────────────────────────
def smart_agent_response(query: str):
    tool_keywords = ["task", "user", "status", "pending", "completed", "id", "email"]
    if not any(keyword in query.lower() for keyword in tool_keywords):
        return "❌ Sorry, this question is beyond my capabilities. Please ask something related to users or tasks."

    result = agent_executor.invoke({"input": query})
    
    for step in result.get("intermediate_steps", []):
        if isinstance(step[1], str):
            return step[1]
    return result.get("output", "🤖 No valid response.")

# ─── FastAPI Server ────────────────────────────────────────────────────────
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    query: str

@app.post("/ask")
async def ask(request: AskRequest):
    try:
        result = smart_agent_response(request.query)
        return {"response": result}
    except Exception as e:
        return {"error": str(e)}

# ─── Entry Point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 Smart Agent running at http://127.0.0.1:8001/ask")
    uvicorn.run(app, host="0.0.0.0", port=8001)
