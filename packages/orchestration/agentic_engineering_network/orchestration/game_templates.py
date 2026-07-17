from __future__ import annotations

import re


def build_game_project_artifacts(idea: str, run_id: str) -> dict[str, str]:
    slug = _slugify(idea)
    base = f"{slug}-{run_id[:8]}"
    title = "3D Pong Arena"
    return {
        f"{base}/README.md": _readme(title, idea),
        f"{base}/.env.example": _env_example(),
        f"{base}/docker-compose.yml": _compose(),
        f"{base}/apps/api/Dockerfile": _api_dockerfile(),
        f"{base}/apps/api/requirements.txt": _api_requirements(),
        f"{base}/apps/api/alembic.ini": _alembic_ini(),
        f"{base}/apps/api/app/__init__.py": "",
        f"{base}/apps/api/app/main.py": _api_main(),
        f"{base}/apps/api/migrations/env.py": _alembic_env(),
        f"{base}/apps/api/migrations/script.py.mako": _alembic_script(),
        f"{base}/apps/api/migrations/versions/0001_initial.py": _alembic_initial_revision(),
        f"{base}/apps/api/tests/test_health.py": _api_test_health(),
        f"{base}/apps/web/Dockerfile": _web_dockerfile(),
        f"{base}/apps/web/package.json": _web_package(),
        f"{base}/apps/web/next.config.ts": _web_next_config(),
        f"{base}/apps/web/tsconfig.json": _web_tsconfig(),
        f"{base}/apps/web/src/app/layout.tsx": _web_layout(title),
        f"{base}/apps/web/src/app/page.tsx": _web_page(),
        f"{base}/apps/web/src/app/globals.css": _web_globals(),
        f"{base}/apps/web/tests/workbench.spec.ts": _web_e2e(),
        f"{base}/apps/desktop/package.json": _desktop_package(title),
        f"{base}/apps/desktop/src/main.js": _desktop_main(title),
        f"{base}/database/schema.sql": _schema_sql(),
        f"{base}/docs/SPEC.md": _spec(idea),
        f"{base}/docs/ARCHITECTURE.md": _architecture(),
        f"{base}/docs/SECURITY.md": _security_doc(),
        f"{base}/docs/PROJECT_KIND.md": "project_kind: game\nprimary_experience: playable_3d_pong\n",
        f"{base}/scripts/start.ps1": _start_script(),
        f"{base}/scripts/test.ps1": _test_script(),
        f"{base}/scripts/package-windows.ps1": _package_windows_script(),
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "generated-game"


def _readme(title: str, idea: str) -> str:
    return f"""# {title}

Generated from:

```text
{idea}
```

## Run

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open:

- Game: http://localhost:13000
- API health: http://localhost:18000/health

## Gameplay

- Move your paddle with `W/S`, `ArrowUp/ArrowDown`, mouse, or touch.
- The AI paddle tracks the ball with limited reaction speed.
- First player to 7 wins.
- Press `Space` to pause/resume.
- Press `R` to restart.

This is a playable game project, not a SaaS dashboard.
"""


def _env_example() -> str:
    return """API_PORT=18000
WEB_PORT=13000
NEXT_PUBLIC_API_URL=http://localhost:18000
"""


def _compose() -> str:
    return """services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: game
      POSTGRES_PASSWORD: change-me
      POSTGRES_DB: game
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U game -d game"]
      interval: 5s
      timeout: 3s
      retries: 20

  api:
    build:
      context: ./apps/api
    ports:
      - "${API_PORT:-18000}:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 10

  web:
    build:
      context: ./apps/web
    environment:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:18000}
    ports:
      - "${WEB_PORT:-13000}:3000"
    depends_on:
      api:
        condition: service_healthy
"""


def _api_dockerfile() -> str:
    return """FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY tests ./tests
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""


def _api_requirements() -> str:
    return """fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pytest>=8.0.0
httpx>=0.27.0
"""


def _api_main() -> str:
    return """from fastapi import FastAPI

app = FastAPI(title="3D Pong Arena API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "3d-pong-arena"}
"""


def _api_test_health() -> str:
    return """from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    assert TestClient(app).get("/health").json()["status"] == "ok"
"""


def _alembic_ini() -> str:
    return """[alembic]
script_location = migrations
sqlalchemy.url = sqlite:///./game.db
"""


def _alembic_env() -> str:
    return """from alembic import context


def run_migrations_offline() -> None:
    context.configure(url="sqlite:///./game.db")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    run_migrations_offline()


run_migrations_online()
"""


def _alembic_script() -> str:
    return """\"\"\"${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
\"\"\"
"""


def _alembic_initial_revision() -> str:
    return '''"""initial game schema

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_scores",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_score", sa.Integer, nullable=False),
        sa.Column("ai_score", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("game_scores")
'''


def _web_dockerfile() -> str:
    return """FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
"""


def _web_package() -> str:
    return """{
  "name": "generated-3d-pong-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -H 0.0.0.0",
    "build": "next build",
    "start": "next start -H 0.0.0.0",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@playwright/test": "^1.57.0",
    "next": "^16.2.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "typescript": "^5.9.0"
  }
}
"""


def _web_next_config() -> str:
    return """import type { NextConfig } from "next";

const nextConfig: NextConfig = {};
export default nextConfig;
"""


def _web_tsconfig() -> str:
    return """{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
"""


def _web_layout(title: str) -> str:
    return f"""import "./globals.css";

export const metadata = {{
  title: "{title}",
  description: "Playable 3D Pong game with score and AI opponent"
}};

export default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{
  return (
    <html lang="en">
      <body>{{children}}</body>
    </html>
  );
}}
"""


def _web_page() -> str:
    return r'''"use client";

import { useEffect, useRef, useState } from "react";

type GameState = {
  player: number;
  ai: number;
  ballX: number;
  ballY: number;
  ballZ: number;
  velocityX: number;
  velocityY: number;
  velocityZ: number;
  playerScore: number;
  aiScore: number;
  paused: boolean;
  winner: string;
};

const initialState = (): GameState => ({
  player: 0,
  ai: 0,
  ballX: 0,
  ballY: 0,
  ballZ: 0,
  velocityX: 0.55,
  velocityY: 0.38,
  velocityZ: 0.72,
  playerScore: 0,
  aiScore: 0,
  paused: false,
  winner: ""
});

export default function Home() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<GameState>(initialState());
  const keysRef = useRef<Set<string>>(new Set());
  const [score, setScore] = useState({ player: 0, ai: 0, winner: "", paused: false });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const activeCanvas = canvas;
    const activeContext = context;

    function resize() {
      activeCanvas.width = Math.floor(activeCanvas.clientWidth * window.devicePixelRatio);
      activeCanvas.height = Math.floor(activeCanvas.clientHeight * window.devicePixelRatio);
    }

    function resetBall(direction: number) {
      const state = stateRef.current;
      state.ballX = 0;
      state.ballY = 0;
      state.ballZ = 0;
      state.velocityX = 0.48 * direction;
      state.velocityY = (Math.random() > 0.5 ? 0.35 : -0.35);
      state.velocityZ = (Math.random() > 0.5 ? 0.68 : -0.68);
    }

    function project(x: number, y: number, z: number) {
      const depth = 900;
      const scale = depth / (depth + z * 220);
      return {
        x: activeCanvas.width / 2 + x * activeCanvas.width * 0.33 * scale,
        y: activeCanvas.height / 2 + y * activeCanvas.height * 0.34 * scale,
        scale
      };
    }

    function drawCourt() {
      const corners = [
        project(-1, -1, -1),
        project(1, -1, -1),
        project(1, 1, -1),
        project(-1, 1, -1),
        project(-1, -1, 1),
        project(1, -1, 1),
        project(1, 1, 1),
        project(-1, 1, 1)
      ];
      activeContext.strokeStyle = "rgba(98, 242, 255, 0.32)";
      activeContext.lineWidth = 2 * window.devicePixelRatio;
      const edges = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
      for (const [a, b] of edges) {
        activeContext.beginPath();
        activeContext.moveTo(corners[a].x, corners[a].y);
        activeContext.lineTo(corners[b].x, corners[b].y);
        activeContext.stroke();
      }
      activeContext.setLineDash([12 * window.devicePixelRatio, 16 * window.devicePixelRatio]);
      activeContext.beginPath();
      const top = project(0, -1, 0);
      const bottom = project(0, 1, 0);
      activeContext.moveTo(top.x, top.y);
      activeContext.lineTo(bottom.x, bottom.y);
      activeContext.stroke();
      activeContext.setLineDash([]);
    }

    function drawPaddle(z: number, y: number, color: string) {
      const center = project(z < 0 ? -0.95 : 0.95, y, z);
      const width = 30 * center.scale * window.devicePixelRatio;
      const height = 130 * center.scale * window.devicePixelRatio;
      activeContext.fillStyle = color;
      activeContext.shadowColor = color;
      activeContext.shadowBlur = 24 * center.scale;
      activeContext.fillRect(center.x - width / 2, center.y - height / 2, width, height);
      activeContext.shadowBlur = 0;
    }

    function drawBall() {
      const state = stateRef.current;
      const ball = project(state.ballX, state.ballY, state.ballZ);
      const radius = 16 * ball.scale * window.devicePixelRatio;
      const gradient = activeContext.createRadialGradient(ball.x - radius / 3, ball.y - radius / 3, radius / 6, ball.x, ball.y, radius);
      gradient.addColorStop(0, "#ffffff");
      gradient.addColorStop(1, "#f8d14a");
      activeContext.fillStyle = gradient;
      activeContext.shadowColor = "#f8d14a";
      activeContext.shadowBlur = 28;
      activeContext.beginPath();
      activeContext.arc(ball.x, ball.y, radius, 0, Math.PI * 2);
      activeContext.fill();
      activeContext.shadowBlur = 0;
    }

    function step() {
      const state = stateRef.current;
      if (!state.paused && !state.winner) {
        const keys = keysRef.current;
        if (keys.has("w") || keys.has("arrowup")) state.player -= 0.045;
        if (keys.has("s") || keys.has("arrowdown")) state.player += 0.045;
        state.player = Math.max(-0.75, Math.min(0.75, state.player));
        state.ai += (state.ballY - state.ai) * 0.045;
        state.ai = Math.max(-0.75, Math.min(0.75, state.ai));
        state.ballX += state.velocityX * 0.018;
        state.ballY += state.velocityY * 0.018;
        state.ballZ += state.velocityZ * 0.018;
        if (Math.abs(state.ballY) > 0.95) state.velocityY *= -1;
        if (Math.abs(state.ballX) > 0.95) state.velocityX *= -1;
        if (state.ballZ < -1) {
          if (Math.abs(state.ballY - state.player) < 0.28) {
            state.ballZ = -1;
            state.velocityZ = Math.abs(state.velocityZ) + 0.035;
            state.velocityY += (state.ballY - state.player) * 0.7;
          } else {
            state.aiScore += 1;
            resetBall(1);
          }
        }
        if (state.ballZ > 1) {
          if (Math.abs(state.ballY - state.ai) < 0.28) {
            state.ballZ = 1;
            state.velocityZ = -Math.abs(state.velocityZ) - 0.035;
            state.velocityY += (state.ballY - state.ai) * 0.55;
          } else {
            state.playerScore += 1;
            resetBall(-1);
          }
        }
        if (state.playerScore >= 7) state.winner = "YOU WIN";
        if (state.aiScore >= 7) state.winner = "AI WINS";
      }
      activeContext.clearRect(0, 0, activeCanvas.width, activeCanvas.height);
      const bg = activeContext.createLinearGradient(0, 0, activeCanvas.width, activeCanvas.height);
      bg.addColorStop(0, "#050713");
      bg.addColorStop(1, "#10192f");
      activeContext.fillStyle = bg;
      activeContext.fillRect(0, 0, activeCanvas.width, activeCanvas.height);
      drawCourt();
      drawPaddle(-1, state.player, "#62f2ff");
      drawPaddle(1, state.ai, "#ff4d8d");
      drawBall();
      setScore({ player: state.playerScore, ai: state.aiScore, winner: state.winner, paused: state.paused });
      requestAnimationFrame(step);
    }

    function keyDown(event: KeyboardEvent) {
      const key = event.key.toLowerCase();
      if (key === " ") stateRef.current.paused = !stateRef.current.paused;
      if (key === "r") stateRef.current = initialState();
      keysRef.current.add(key);
    }
    function keyUp(event: KeyboardEvent) {
      keysRef.current.delete(event.key.toLowerCase());
    }
    function pointer(event: PointerEvent) {
      const rect = activeCanvas.getBoundingClientRect();
      const y = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      stateRef.current.player = Math.max(-0.75, Math.min(0.75, y));
    }

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    activeCanvas.addEventListener("pointermove", pointer);
    const frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
      activeCanvas.removeEventListener("pointermove", pointer);
    };
  }, []);

  return (
    <main className="game-shell">
      <section className="hud">
        <div>
          <p>3D PONG ARENA</p>
          <h1>{score.player} : {score.ai}</h1>
        </div>
        <div className="status">{score.winner || (score.paused ? "PAUSED" : "FIRST TO 7")}</div>
      </section>
      <canvas ref={canvasRef} className="game-canvas" aria-label="Playable 3D Pong arena" />
      <section className="controls">
        <span>W/S or Arrow keys</span>
        <span>Mouse/touch moves paddle</span>
        <span>Space pause</span>
        <span>R restart</span>
      </section>
    </main>
  );
}
'''


def _web_globals() -> str:
    return """* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: #050713; color: #f8fbff; font-family: Arial, Helvetica, sans-serif; overflow: hidden; }
button, input { font: inherit; }
.game-shell { min-height: 100vh; display: grid; grid-template-rows: auto 1fr auto; padding: 18px; gap: 14px; background: radial-gradient(circle at 50% 20%, rgba(98,242,255,.18), transparent 34%), #050713; }
.hud { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.hud p { margin: 0; color: #62f2ff; font-size: 12px; letter-spacing: .14em; }
.hud h1 { margin: 4px 0 0; font-size: clamp(34px, 6vw, 72px); line-height: 1; }
.status { border: 1px solid rgba(98,242,255,.45); border-radius: 8px; padding: 10px 14px; color: #f8d14a; background: rgba(5,7,19,.65); }
.game-canvas { width: 100%; height: 100%; min-height: 0; border: 1px solid rgba(98,242,255,.3); border-radius: 10px; background: #050713; box-shadow: 0 20px 80px rgba(0,0,0,.4); touch-action: none; }
.controls { display: flex; flex-wrap: wrap; gap: 10px; color: #9fb6d6; font-size: 13px; }
.controls span { border: 1px solid rgba(255,255,255,.14); border-radius: 999px; padding: 8px 10px; background: rgba(255,255,255,.04); }
"""


def _web_e2e() -> str:
    return """import { expect, test } from "@playwright/test";

test("loads playable pong arena", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("3D PONG ARENA")).toBeVisible();
  await expect(page.locator("canvas[aria-label='Playable 3D Pong arena']")).toBeVisible();
});
"""


def _desktop_package(title: str) -> str:
    return f"""{{
  "name": "generated-3d-pong-desktop",
  "version": "0.1.0",
  "private": true,
  "main": "src/main.js",
  "scripts": {{
    "package": "echo Desktop wrapper scaffold for {title}"
  }}
}}
"""


def _desktop_main(title: str) -> str:
    return f"""console.log("{title} desktop wrapper scaffold");
"""


def _schema_sql() -> str:
    return """CREATE TABLE IF NOT EXISTS game_scores (
  id SERIAL PRIMARY KEY,
  player_score INTEGER NOT NULL,
  ai_score INTEGER NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _spec(idea: str) -> str:
    return f"""# 3D Pong Arena Spec

Prompt:

```text
{idea}
```

## Acceptance Criteria

- Render a playable Pong arena, not a SaaS dashboard.
- Show player and AI scores.
- Provide AI opponent movement.
- Support keyboard and pointer controls.
- Provide pause and restart.
- First player to 7 wins.
"""


def _architecture() -> str:
    return """# Architecture

The game is implemented as a Next.js client-rendered canvas experience. The API is intentionally minimal and provides health checks for Docker orchestration. Gameplay runs locally in the browser animation loop.
"""


def _security_doc() -> str:
    return """# Security

No secrets are required for local gameplay. The app does not collect user data by default.
"""


def _start_script() -> str:
    return """$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\\..
docker compose up --build
"""


def _test_script() -> str:
    return """$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\\..
docker compose run --rm api pytest -q
docker compose run --rm web npm run build
"""


def _package_windows_script() -> str:
    return """$ErrorActionPreference = "Stop"
Write-Host "Desktop package scaffold present. Use the web game at http://localhost:13000."
"""
