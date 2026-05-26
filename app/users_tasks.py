from fastapi import FastAPI, HTTPException, Response, status, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import psycopg2, time
from psycopg2.extras import RealDictCursor
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import agent_executor
  # agent.py lives at project root

# ─── FastAPI APP ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Users & Tasks API",
    description="Manage users, tasks, and ask an offline AI assistant",
    version="1.0.0"
)



# ─── Basic Auth Setup ────────────────────────────────────────────────────────

# ─── CORS Setup ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Schemas ────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    name: str = Field(..., example="Anirudh Raj")
    email: EmailStr = Field(..., example="anirudh@example.com")

class UserOut(UserCreate):
    id: int

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = Field(..., example="pending")
    user_id: int

class TaskOut(TaskCreate):
    id: int

class AgentQuery(BaseModel):
    question: str = Field(..., example="List pending tasks for Anirudh")

class AgentAnswer(BaseModel):
    answer: str

# ─── Database Connection ──────────────────────────────────────────────────────
while True:
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="fastapi",
            user="postgres",
            password="Hellocheck9@",
            cursor_factory=RealDictCursor,
        )
        cursor = conn.cursor()
        print("Database connection was successful ✅")
        break
    except Exception as err:
        print("DB connection failed ⇒", err)
        time.sleep(5)

# ─── Root Endpoint ───────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "Welcome to Users & Tasks API"}

# ─── User Routes ─────────────────────────────────────────────────────────────
@app.get("/users", response_model=List[UserOut])
def get_users(
    name: Optional[str] = Query(None),
    limit: int = 100,
    skip: int = 0,
    
):
    if name:
        cursor.execute(
            "SELECT * FROM users WHERE name ILIKE %s LIMIT %s OFFSET %s",
            (f"%{name}%", limit, skip),
        )
    else:
        cursor.execute("SELECT * FROM users LIMIT %s OFFSET %s", (limit, skip))
    return cursor.fetchall()

@app.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate):
    cursor.execute(
        "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING *",
        (user.name, user.email),
    )
    new_user = cursor.fetchone()
    conn.commit()
    return new_user

@app.get("/users/{id}", response_model=UserOut)
def get_user(id: int):
    cursor.execute("SELECT * FROM users WHERE id = %s", (id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{id}", response_model=UserOut)
def update_user(id: int, user: UserCreate):
    cursor.execute(
        "UPDATE users SET name=%s, email=%s WHERE id=%s RETURNING *",
        (user.name, user.email, id),
    )
    upd = cursor.fetchone()
    if not upd:
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    return upd

@app.delete("/users/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(id: int):
    cursor.execute("DELETE FROM users WHERE id=%s RETURNING *", (id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# ─── Task Routes ─────────────────────────────────────────────────────────────
@app.get("/tasks", response_model=List[TaskOut])
def get_tasks(
    title: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    limit: int = 10,
    skip: int = 0,
):
    q = "SELECT * FROM tasks WHERE true"
    p: list = []
    if title:
        q += " AND title ILIKE %s"; p.append(f"%{title}%")
    if status:
        q += " AND status ILIKE %s"; p.append(status)
    if user_id:
        q += " AND user_id = %s"; p.append(user_id)
    q += " LIMIT %s OFFSET %s"; p.extend([limit, skip])
    cursor.execute(q, tuple(p))
    return cursor.fetchall()

@app.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate):
    cursor.execute(
        "INSERT INTO tasks (title, description, status, user_id) "
        "VALUES (%s, %s, %s, %s) RETURNING *",
        (task.title, task.description, task.status, task.user_id),
    )
    new_task = cursor.fetchone()
    conn.commit()
    return new_task

@app.put("/tasks/{id}", response_model=TaskOut)
def update_task(id: int, task: TaskCreate):
    cursor.execute(
        "UPDATE tasks SET title=%s, description=%s, status=%s, user_id=%s "
        "WHERE id=%s RETURNING *",
        (task.title, task.description, task.status, task.user_id, id),
    )
    upd = cursor.fetchone()
    if not upd:
        raise HTTPException(status_code=404, detail="Task not found")
    conn.commit()
    return upd

@app.delete("/tasks/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(id: int):
    cursor.execute("DELETE FROM tasks WHERE id = %s RETURNING *", (id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/tasks/pending", response_model=List[TaskOut])
def get_pending_tasks(username: Optional[str] = Query(None), user_id: Optional[int] = Query(None)):
    if not username and not user_id:
        raise HTTPException(status_code=400, detail="Provide username or user_id")
    if user_id:
        cursor.execute("SELECT * FROM tasks WHERE user_id=%s AND status ILIKE 'pending'", (user_id,))
        return cursor.fetchall()
    clean = username.strip().lower()
    cursor.execute("SELECT id FROM users WHERE LOWER(name) ILIKE %s", (f"%{clean}%",))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    cursor.execute("SELECT * FROM tasks WHERE user_id=%s AND status ILIKE 'pending'", (user["id"],))
    return cursor.fetchall()

@app.get("/tasks/{id}", response_model=TaskOut)
def get_task(id: int):
    cursor.execute("SELECT * FROM tasks WHERE id=%s", (id,))
    task = cursor.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

# ─── AI Agent Route ──────────────────────────────────────────────────────────
@app.post("/agent/ask", response_model=AgentAnswer)
async def ask_agent(query: AgentQuery):
    try:
        response = agent_executor.invoke({"input": query.question})
        return {"answer": response.get("output", "🤖 No valid response.")}
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(err)}")

