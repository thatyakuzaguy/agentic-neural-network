"use client";

import { Building2, GripVertical, Maximize2, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { PanelId, panelDefinitions, usePanel } from "@/components/panels";

const defaultOrder = panelDefinitions.map((panel) => panel.id);

function panelSizeClass(size: "large" | "medium" | "small") {
  if (size === "large") return "h-[560px] w-[min(760px,100%)]";
  if (size === "small") return "h-[320px] w-[min(360px,100%)]";
  return "h-[420px] w-[min(520px,100%)]";
}

function openDetachedPanel(panelId: PanelId) {
  const url = `${window.location.origin}${window.location.pathname}?panel=${panelId}`;
  window.open(url, `aen-${panelId}`, "width=960,height=760,left=120,top=80,resizable=yes,scrollbars=no");
}

function PanelSurface({
  panelId,
  index,
  onDropPanel,
  detached = false
}: {
  panelId: PanelId;
  index: number;
  onDropPanel: (from: number, to: number) => void;
  detached?: boolean;
}) {
  const definition = panelDefinitions.find((panel) => panel.id === panelId) ?? panelDefinitions[0];
  const Content = definition.component;

  return (
    <section
      className={[
        "flex min-h-[260px] min-w-[320px] flex-col overflow-hidden border border-line bg-panel shadow-[0_16px_40px_rgba(0,0,0,0.24)]",
        detached ? "h-screen w-screen resize-none border-0" : `resize ${panelSizeClass(definition.size)}`
      ].join(" ")}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const from = Number(event.dataTransfer.getData("text/plain"));
        if (!Number.isNaN(from)) onDropPanel(from, index);
      }}
      onDragEnter={(event) => event.currentTarget.classList.add("border-accent")}
      onDragLeave={(event) => event.currentTarget.classList.remove("border-accent")}
    >
      <header
        className="flex h-10 shrink-0 items-center justify-between border-b border-line bg-panel2 px-2"
        draggable={!detached}
        onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
      >
        <div className="flex min-w-0 items-center gap-2">
          <GripVertical size={15} className={detached ? "text-muted" : "cursor-grab text-muted"} />
          <h2 className="truncate text-sm font-semibold text-text">{definition.title}</h2>
        </div>
        {!detached ? (
          <button
            className="grid h-7 w-7 place-items-center rounded border border-line text-muted hover:border-accent hover:text-accent"
            onClick={() => openDetachedPanel(definition.id)}
            title="Open in separate window"
            type="button"
          >
            <Maximize2 size={14} />
          </button>
        ) : null}
      </header>
      <div className="scrollbar min-h-0 flex-1 overflow-auto">
        <Content />
      </div>
    </section>
  );
}

export function Workbench() {
  const [order, setOrder] = useState<PanelId[]>(defaultOrder);
  const [singlePanelId, setSinglePanelId] = useState<string | null>(null);
  const singlePanel = usePanel(singlePanelId);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSinglePanelId(params.get("panel"));
    const saved = window.localStorage.getItem("aen-panel-order");
    if (saved) {
      const parsed = JSON.parse(saved) as PanelId[];
      const valid = parsed.filter((id) => defaultOrder.includes(id));
      setOrder([...valid, ...defaultOrder.filter((id) => !valid.includes(id))]);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("aen-panel-order", JSON.stringify(order));
  }, [order]);

  const orderedPanels = useMemo(
    () => order.map((id) => panelDefinitions.find((panel) => panel.id === id)).filter(Boolean),
    [order]
  );

  function movePanel(from: number, to: number) {
    setOrder((current) => {
      const next = [...current];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }

  if (singlePanelId) {
    return (
      <main className="h-screen bg-canvas">
        <PanelSurface panelId={singlePanel.id} index={0} onDropPanel={() => undefined} detached />
      </main>
    );
  }

  return (
    <main className="flex h-screen flex-col bg-canvas">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-panel px-4">
        <div>
          <h1 className="text-base font-semibold">Agentic Engineering Network</h1>
          <p className="text-xs text-muted">Resizable local multi-agent engineering workbench</p>
        </div>
        <div className="flex items-center gap-2">
          <a
            className="inline-flex h-8 items-center gap-2 rounded border border-line px-3 text-xs text-muted hover:border-accent hover:text-accent"
            href="/agent-office"
          >
            <Building2 size={14} />
            Agent Office
          </a>
          <button
            className="inline-flex h-8 items-center gap-2 rounded border border-line px-3 text-xs text-muted hover:border-accent hover:text-accent"
            onClick={() => setOrder(defaultOrder)}
            type="button"
          >
            <RotateCcw size={14} />
            Reset layout
          </button>
        </div>
      </header>
      <div className="scrollbar flex-1 overflow-auto p-3">
        <div className="flex flex-wrap content-start items-start gap-3">
          {orderedPanels.map((panel, index) =>
            panel ? (
              <PanelSurface key={panel.id} panelId={panel.id} index={index} onDropPanel={movePanel} />
            ) : null
          )}
        </div>
      </div>
    </main>
  );
}
