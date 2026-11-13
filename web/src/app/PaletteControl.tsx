import { useEffect, useState } from "react";

import { Select } from "../components/ui";
import { useI18n } from "../i18n/useI18n";

type Palette = "pencil" | "ochre" | "graphite";

function parsePalette(value: string | null): Palette {
  return value === "ochre" || value === "graphite" ? value : "pencil";
}

export function PaletteControl() {
  const { t } = useI18n();
  const [palette, setPalette] = useState<Palette>(() =>
    parsePalette(localStorage.getItem("datakeel.palette")),
  );
  useEffect(() => {
    localStorage.setItem("datakeel.palette", palette);
    if (palette === "pencil")
      document.documentElement.removeAttribute("data-palette");
    else document.documentElement.dataset.palette = palette;
  }, [palette]);
  return (
    <Select
      className="palette-control"
      size="sm"
      aria-label={t("palette")}
      value={palette}
      onBlur={(event) => {
        setPalette(parsePalette(event.target.value));
      }}
      onChange={(event) => {
        setPalette(parsePalette(event.target.value));
      }}
    >
      <option value="pencil">{t("palettePencil")}</option>
      <option value="ochre">{t("paletteOchre")}</option>
      <option value="graphite">{t("paletteGraphite")}</option>
    </Select>
  );
}
