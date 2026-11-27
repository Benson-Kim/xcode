import {
  SUMMARY_GEOMETRY as G,
  type SummaryCell,
  type SummaryLayout,
} from "./summaryImage";

const FACE = "Figtree, system-ui, sans-serif";
const INK = "#06283A";
const SLATE = "#547079";
const TEAL = "#0F766E";
const RED = "#B3261E";
const AMBER = "#8A6100";
const TOTAL_INK = "#0B5A54";
const REG_WIDTH = 170;
const WEEK_WIDTH = 150;
const FIGURE_STEP = 170;

type Pen = CanvasRenderingContext2D;

async function loadFaces(doc: Document) {
  const fonts = doc.fonts;
  if (!fonts?.load) return;
  await Promise.all(
    ["800 40px Figtree", "700 40px Figtree", "600 40px Figtree"].map((face) =>
      fonts.load(face).catch(() => []),
    ),
  );
}

function write(
  pen: Pen,
  text: string,
  x: number,
  y: number,
  font: string,
  colour: string,
  align: CanvasTextAlign = "left",
  max?: number,
) {
  pen.font = `${font} ${FACE}`;
  pen.fillStyle = colour;
  pen.textAlign = align;
  let shown = text;
  if (max !== undefined && pen.measureText(shown).width > max) {
    while (shown && pen.measureText(`${shown}…`).width > max)
      shown = shown.slice(0, -1);
    shown = `${shown.trimEnd()}…`;
  }
  pen.fillText(shown, x, y);
}

function card(pen: Pen, x: number, y: number, w: number, h: number, r: number) {
  pen.fillStyle = "#FFFFFF";
  pen.beginPath();
  pen.moveTo(x + r, y);
  pen.arcTo(x + w, y, x + w, y + h, r);
  pen.arcTo(x + w, y + h, x, y + h, r);
  pen.arcTo(x, y + h, x, y, r);
  pen.arcTo(x, y, x + w, y, r);
  pen.closePath();
  pen.fill();
}

function drawCell(
  pen: Pen,
  cell: SummaryCell,
  x: number,
  mid: number,
  width: number,
) {
  switch (cell.state) {
    case "missing":
      return write(pen, cell.text, x, mid + 8, "700 19px", RED, "right");
    case "due":
      return write(pen, cell.text, x, mid + 8, "600 19px", SLATE, "right");
    case "reason":
      return write(
        pen,
        cell.text,
        x,
        mid + 8,
        "700 17px",
        AMBER,
        "right",
        width,
      );
    case "amount":
      write(
        pen,
        cell.text,
        x,
        cell.note ? mid : mid + 9,
        "700 24px",
        INK,
        "right",
      );
      if (cell.note)
        write(
          pen,
          cell.note,
          x,
          mid + 24,
          "700 17px",
          cell.fuelNote ? SLATE : AMBER,
          "right",
          width,
        );
      return;
    case "blank":
      return;
  }
}

// Draws the summary image on a canvas of the layout's size: the header band (title, period, Missing days and Low
// days), then the table on a white card, as the owner's sample (Web v2.46).
export async function drawSummaryImage(
  layout: SummaryLayout,
  doc: Document = document,
): Promise<HTMLCanvasElement> {
  await loadFaces(doc);
  const canvas = doc.createElement("canvas");
  canvas.width = layout.width;
  canvas.height = layout.height;
  const pen = canvas.getContext("2d");
  if (!pen) throw new Error("This browser cannot draw the image.");

  const W = layout.width;
  const H = layout.height;
  const L = G.pad + 16;
  const R = W - G.pad - 16;
  const rows = layout.rows.length;

  const band = pen.createLinearGradient(0, 0, W * 0.35, G.header);
  band.addColorStop(0, "#04202F");
  band.addColorStop(0.52, "#06364A");
  band.addColorStop(1, "#0A5560");
  pen.fillStyle = band;
  pen.fillRect(0, 0, W, G.header);
  const figuresLeft = R - layout.figures.length * FIGURE_STEP;
  write(pen, layout.title, L, 58, "800 34px", "#FFFFFF");
  write(
    pen,
    layout.subtitle,
    L,
    96,
    "600 22px",
    "rgba(255,255,255,.78)",
    "left",
    figuresLeft - L,
  );
  layout.figures.forEach((figure, index) => {
    const x = R - (layout.figures.length - 1 - index) * FIGURE_STEP;
    write(
      pen,
      figure.label,
      x,
      52,
      "700 19px",
      "rgba(255,255,255,.6)",
      "right",
    );
    write(
      pen,
      figure.value,
      x,
      98,
      "800 40px",
      figure.alert ? "#FFB4AB" : "#FFFFFF",
      "right",
    );
  });

  pen.fillStyle = "#F2F7F8";
  pen.fillRect(0, G.header, W, H - G.header);
  const dayLeft = L + REG_WIDTH;
  const dayWidth = (R - WEEK_WIDTH - dayLeft) / Math.max(layout.days.length, 1);
  const dayRight = (index: number) => dayLeft + dayWidth * (index + 1) - 10;
  const top = G.tableTop;
  card(
    pen,
    G.pad,
    G.cardTop,
    W - 2 * G.pad,
    top - G.cardTop + (Math.max(rows, 1) + 1) * G.row + 16,
    22,
  );

  write(pen, "Vehicle", L, top - 30, "700 20px", SLATE);
  layout.days.forEach((day, index) => {
    write(
      pen,
      day.weekday,
      dayRight(index),
      top - 42,
      "700 20px",
      day.today ? TEAL : SLATE,
      "right",
    );
    write(
      pen,
      day.day,
      dayRight(index),
      top - 16,
      "800 22px",
      day.today ? TEAL : INK,
      "right",
    );
  });
  write(pen, "Week", R, top - 30, "700 20px", SLATE, "right");
  pen.fillStyle = "#D5E2E5";
  pen.fillRect(L, top, R - L, 2);

  layout.rows.forEach((row, index) => {
    const y = top + index * G.row;
    const mid = y + G.row / 2;
    if (index) {
      pen.fillStyle = "#E8F0F2";
      pen.fillRect(L, y, R - L, 2);
    }
    write(
      pen,
      row.registration,
      L,
      row.missing ? mid - 2 : mid + 10,
      "800 28px",
      INK,
      "left",
      REG_WIDTH - 8,
    );
    if (row.missing) write(pen, row.missing, L, mid + 26, "700 19px", RED);
    row.cells.forEach((cell, day) =>
      drawCell(pen, cell, dayRight(day), mid, dayWidth - 12),
    );
    write(pen, row.total, R, mid + 10, "800 28px", INK, "right");
  });
  if (!rows) write(pen, "No vehicles in view.", L, top + 56, "600 26px", SLATE);

  const foot = top + Math.max(rows, 1) * G.row;
  const base = foot + G.row / 2;
  pen.fillStyle = "#DDF3F0";
  pen.fillRect(L - 8, foot + 6, R - L + 16, G.row - 12);
  write(pen, "Total", L, base + 9, "800 24px", TOTAL_INK);
  layout.dayTotals.forEach((total, index) => {
    if (total !== null)
      write(
        pen,
        total,
        dayRight(index),
        base + 9,
        "800 22px",
        TOTAL_INK,
        "right",
      );
  });
  write(pen, layout.total, R, base + 10, "800 28px", TOTAL_INK, "right");
  return canvas;
}

export function canvasBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) =>
        blob
          ? resolve(blob)
          : reject(new Error("The image could not be made.")),
      "image/png",
    ),
  );
}
