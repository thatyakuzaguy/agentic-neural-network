import { execFile } from "node:child_process";
import os from "node:os";
import { promisify } from "node:util";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const execFileAsync = promisify(execFile);

type CpuSnapshot = {
  idle: number;
  total: number;
};

type GpuEngineMetric = {
  engine: string;
  utilizationPercent: number;
};

let previousCpuSnapshot: CpuSnapshot | null = null;
let cachedGpuEngines: GpuEngineMetric[] = [];
let cachedGpuEnginesAt = 0;
let pendingGpuEngines: Promise<GpuEngineMetric[]> | null = null;

function round(value: number, digits = 1): number {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function currentCpuSnapshot(): CpuSnapshot {
  return os.cpus().reduce(
    (acc, cpu) => {
      const total = Object.values(cpu.times).reduce((sum, value) => sum + value, 0);
      return {
        idle: acc.idle + cpu.times.idle,
        total: acc.total + total,
      };
    },
    { idle: 0, total: 0 },
  );
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function cpuPercent(): Promise<number> {
  const current = currentCpuSnapshot();
  const previous = previousCpuSnapshot;
  previousCpuSnapshot = current;
  if (!previous) {
    await delay(120);
    return cpuPercent();
  }

  const idleDelta = current.idle - previous.idle;
  const totalDelta = current.total - previous.total;
  if (totalDelta <= 0) {
    return 0;
  }
  return round(Math.max(0, Math.min(100, (1 - idleDelta / totalDelta) * 100)), 0);
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) {
    return `${days}d ${hours}h`;
  }
  return `${hours}h ${minutes}m`;
}

async function queryGpu() {
  const args = [
    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
    "--format=csv,noheader,nounits",
  ];
  const { stdout } = await execFileAsync("nvidia-smi", args, {
    timeout: 1800,
    windowsHide: true,
  });
  const firstLine = stdout.trim().split(/\r?\n/)[0] ?? "";
  const [name = "Unavailable", gpu = "0", used = "0", total = "0", temperature = "0"] = firstLine
    .split(",")
    .map((part) => part.trim());

  return {
    name,
    utilizationPercent: Number.parseFloat(gpu) || 0,
    memoryUsedMb: Number.parseFloat(used) || 0,
    memoryTotalMb: Number.parseFloat(total) || 0,
    temperatureC: Number.parseFloat(temperature) || 0,
  };
}

async function queryWindowsGpuEngines(): Promise<GpuEngineMetric[]> {
  if (process.platform !== "win32") {
    return [];
  }

  const command = [
    "$samples = (Get-Counter '\\GPU Engine(*)\\Utilization Percentage').CounterSamples",
    "$samples | Where-Object { $_.CookedValue -gt 0 } | Select-Object InstanceName,CookedValue | ConvertTo-Json -Compress",
  ].join("; ");
  const { stdout } = await execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
    { timeout: 8000, windowsHide: true },
  );
  const trimmed = stdout.trim();
  if (!trimmed) {
    return [];
  }

  const parsed = JSON.parse(trimmed) as
    | { InstanceName?: string; CookedValue?: number }
    | { InstanceName?: string; CookedValue?: number }[];
  const samples = Array.isArray(parsed) ? parsed : [parsed];
  const byEngine = new Map<string, number>();

  for (const sample of samples) {
    const instanceName = sample.InstanceName ?? "";
    const cookedValue = Number(sample.CookedValue ?? 0);
    const engine = instanceName.includes("_engtype_")
      ? instanceName.split("_engtype_").pop() || "unknown"
      : "unknown";
    byEngine.set(engine, (byEngine.get(engine) ?? 0) + cookedValue);
  }

  return [...byEngine.entries()]
    .map(([engine, utilizationPercent]) => ({
      engine,
      utilizationPercent: round(Math.max(0, Math.min(100, utilizationPercent)), 0),
    }))
    .sort((a, b) => b.utilizationPercent - a.utilizationPercent);
}

async function getWindowsGpuEngines(): Promise<GpuEngineMetric[]> {
  const now = Date.now();
  if (now - cachedGpuEnginesAt < 2500) {
    return cachedGpuEngines;
  }
  if (pendingGpuEngines) {
    return cachedGpuEngines.length > 0 ? cachedGpuEngines : pendingGpuEngines;
  }

  pendingGpuEngines = queryWindowsGpuEngines()
    .then((metrics) => {
      cachedGpuEngines = metrics;
      cachedGpuEnginesAt = Date.now();
      return metrics;
    })
    .finally(() => {
      pendingGpuEngines = null;
    });

  return cachedGpuEngines.length > 0 ? cachedGpuEngines : pendingGpuEngines;
}

async function queryGpuProcesses() {
  try {
    const { stdout } = await execFileAsync(
      "nvidia-smi",
      ["--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
      { timeout: 1800, windowsHide: true },
    );
    return stdout
      .trim()
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => Boolean(line) && line.includes(","))
      .map((line, index) => {
        const [pid = "unknown", processName = "gpu-process", memoryMb = "0"] = line
          .split(",")
          .map((part) => part.trim());
        const parsedMemoryMb = Number.parseFloat(memoryMb);
        const normalizedName = processName.toLowerCase();
        const looksLikeModelRuntime = /python|llama|ollama|text-generation|vllm|server|node/.test(normalizedName);
        if (!/^\d+$/.test(pid) || !Number.isFinite(parsedMemoryMb) || parsedMemoryMb <= 0 || !looksLikeModelRuntime) {
          return null;
        }
        return {
          id: `gpu-process-${pid}-${index}`,
          name: processName.split(/[\\/]/).pop() || processName,
          status: "loaded",
          tps: 0,
          usedVramGb: round(parsedMemoryMb / 1024, 1),
        };
      })
      .filter((process): process is NonNullable<typeof process> => process !== null);
  } catch {
    return [];
  }
}

export async function GET() {
  const errors: string[] = [];
  const ramTotalGb = os.totalmem() / 1024 ** 3;
  const ramFreeGb = os.freemem() / 1024 ** 3;
  let gpu = {
    name: "Unavailable",
    utilizationPercent: 0,
    memoryUsedMb: 0,
    memoryTotalMb: 0,
    temperatureC: 0,
  };

  try {
    gpu = await queryGpu();
  } catch (error) {
    errors.push(error instanceof Error ? error.message : "nvidia-smi unavailable");
  }

  let gpuEngines: GpuEngineMetric[] = [];
  try {
    gpuEngines = await getWindowsGpuEngines();
  } catch (error) {
    errors.push(error instanceof Error ? error.message : "Windows GPU counters unavailable");
  }

  const loadedModels = await queryGpuProcesses();
  const activeProcess = loadedModels[0];
  const windowsGpuPercent = gpuEngines[0]?.utilizationPercent;
  const gpuPercent = windowsGpuPercent ?? round(gpu.utilizationPercent, 0);

  return NextResponse.json(
    {
      status: errors.length > 0 ? "partial" : "live",
      sampledAt: new Date().toISOString(),
      pollMs: 1000,
      compute: {
        gpuPercent,
        gpuCudaPercent: round(gpu.utilizationPercent, 0),
        gpuSource: windowsGpuPercent == null ? "nvidia-smi" : "windows-gpu-engine",
        gpuEngines,
        cpuPercent: await cpuPercent(),
        gpuTemperatureC: round(gpu.temperatureC, 0),
      },
      memory: {
        vramUsedGb: round(gpu.memoryUsedMb / 1024, 1),
        vramTotalGb: round(gpu.memoryTotalMb / 1024, 1),
        ramUsedGb: round(ramTotalGb - ramFreeGb, 1),
        ramTotalGb: round(ramTotalGb, 1),
      },
      inference: {
        activeModel: activeProcess?.name ?? "No model loaded",
        activeStage: activeProcess ? `GPU process PID ${activeProcess.id.split("-")[2]}` : "Idle",
        tokensPerSec: 0,
        loadedModels,
      },
      system: {
        gpuModel: gpu.name,
        uptime: formatUptime(os.uptime()),
        pipelineId: "Idle",
        source: windowsGpuPercent == null
          ? "local nvidia-smi + OS telemetry"
          : "Windows GPU Engine counters + nvidia-smi memory + OS telemetry",
      },
      errors,
    },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
