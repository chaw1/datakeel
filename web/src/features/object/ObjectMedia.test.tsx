import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { dataset, file, version } from "../../test/fixtures";

import { readObjectTarget } from "./navigation";
import { ObjectMedia } from "./ObjectMedia";
import { ObjectSections } from "./ObjectSections";
import { objectData } from "./testFixtures";

import type { ObjectData } from "../../api/objects";
import type { FileItem } from "../../api/types";

const source: FileItem = {
  ...file,
  id: "camera",
  filename: "camera.mkv",
  modality: "video",
};
const media: NonNullable<FileItem["media"]> = {
  probe: {
    duration_ms: 12000,
    width: 160,
    height: 120,
    frame_rate: 30,
    rotation: 0,
    codec: "ffv1",
    format: "matroska",
    audio_tracks: 1,
    sample_rate: 16000,
    channels: 1,
  },
  issues: [
    { code: "black_frame", start_ms: 0, end_ms: 1000, severity: "warning" },
  ],
  source_start_ms: 0,
  history: [],
};
const clip: FileItem = {
  ...source,
  id: "clip-1",
  filename: "camera-clip.mkv",
  media: {
    ...media,
    source_asset_id: source.id,
    source_file_id: source.id,
    source_start_ms: 1000,
    source_end_ms: 4000,
    history: [
      {
        operator: "video.segment",
        version: "1.0.0",
        parameters: {},
        parameters_digest: "digest",
        source_file_id: source.id,
        start_ms: 1000,
        end_ms: 4000,
      },
    ],
  },
};
const target = {
  kind: "file",
  id: source.id,
  datasetId: dataset.id,
  tab: "facts",
} as const;
const measuredVersion = {
  ...version,
  id: "version-measured",
  created_at: version.created_at + 1,
  manifest: [{ ...source, media }, clip],
};
const data: ObjectData = {
  ...objectData,
  target,
  file: source,
  versions: [measuredVersion, { ...version, manifest: [source] }],
};

it("shows measurements and defect intervals from the newest matching recording", () => {
  render(<ObjectMedia data={data} target={target} />);
  const section = screen.getByRole("region", { name: "Audio and video" });
  expect(within(section).getByText("12.000 s")).toBeVisible();
  expect(within(section).getByText("160 × 120")).toBeVisible();
  expect(within(section).getByText(/Black frames/)).toHaveTextContent(
    "0.000–1.000 s",
  );
  const link = within(section).getByRole("link", { name: clip.filename });
  expect(readObjectTarget(link.getAttribute("href") ?? "")).toMatchObject({
    kind: "file",
    id: clip.id,
    versionId: measuredVersion.id,
    tab: "facts",
  });
  expect(link.parentElement).toHaveTextContent("1.000–4.000 s");
});

it("deduplicates retained clips while linking the latest immutable manifest", () => {
  render(
    <ObjectMedia
      data={{
        ...data,
        versions: [
          {
            ...measuredVersion,
            id: "version-latest",
            created_at: measuredVersion.created_at + 1,
          },
          measuredVersion,
        ],
      }}
      target={target}
    />,
  );
  expect(screen.getAllByRole("link", { name: clip.filename })).toHaveLength(1);
  expect(
    readObjectTarget(
      screen.getByRole("link", { name: clip.filename }).getAttribute("href") ??
        "",
    )?.versionId,
  ).toBe("version-latest");
});

it("does not borrow later measurements when a source version is pinned", () => {
  render(
    <ObjectMedia data={data} target={{ ...target, versionId: version.id }} />,
  );
  expect(
    screen.getByText("No measurements are available for this version."),
  ).toBeVisible();
  expect(screen.queryByText("12.000 s")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: clip.filename }),
  ).not.toBeInTheDocument();
});

it("shows derived clips even when only the source file lacks measurements", () => {
  render(
    <ObjectMedia
      data={{ ...data, versions: [{ ...measuredVersion, manifest: [clip] }] }}
      target={target}
    />,
  );
  expect(
    screen.getByText("No measurements are available for this version."),
  ).toBeVisible();
  expect(screen.getByRole("link", { name: clip.filename })).toBeVisible();
  expect(
    screen.queryByText("No signal issues detected."),
  ).not.toBeInTheDocument();
});

it("shows the pinned measurement instead of the newer measurement", () => {
  const earlier = {
    ...version,
    manifest: [
      {
        ...source,
        media: { ...media, probe: { ...media.probe, duration_ms: 9000 } },
      },
    ],
  };
  render(
    <ObjectMedia
      data={{ ...data, version: earlier, versions: [measuredVersion, earlier] }}
      target={{ ...target, versionId: earlier.id }}
    />,
  );
  expect(screen.getByText("9.000 s")).toBeVisible();
  expect(screen.queryByText("12.000 s")).not.toBeInTheDocument();
});

it("shows clip provenance, operator version and explicit alignment confidence", () => {
  const alignedClip = {
    ...clip,
    media: {
      ...media,
      ...clip.media,
      alignment: {
        reference_file_id: source.id,
        offset_ms: 500,
        confidence: 0.98,
        aligned: true,
        reason: "matched" as const,
      },
    },
  };
  render(
    <ObjectMedia
      data={{ ...data, file: alignedClip, versions: [] }}
      target={{ ...target, id: clip.id }}
    />,
  );
  expect(screen.getByText(/Offset 500 ms/)).toBeVisible();
  expect(screen.getByText(/Confidence 98.0%/)).toBeVisible();
  expect(
    readObjectTarget(
      screen
        .getByRole("link", { name: "Source recording" })
        .getAttribute("href") ?? "",
    )?.id,
  ).toBe(source.id);
  expect(screen.getByText(/video.segment/)).toHaveTextContent("1.0.0");
});

it("localizes audio failures and leaves unknown signal codes visible", () => {
  const microphone = {
    ...source,
    id: "microphone",
    modality: "audio",
    media: {
      ...media,
      probe: { ...media.probe, width: 0, height: 0 },
      alignment: {
        reference_file_id: source.id,
        offset_ms: null,
        confidence: 0,
        aligned: false,
        reason: "ambiguous" as const,
      },
      issues: [
        {
          code: "future_issue",
          start_ms: 2000,
          end_ms: 3000,
          severity: "warning" as const,
        },
      ],
    },
  };
  render(
    <I18nContext
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <ObjectMedia
        data={{ ...data, file: microphone }}
        target={{ ...target, id: microphone.id }}
      />
    </I18nContext>,
  );
  expect(screen.getByText(/无法对齐/)).toBeVisible();
  expect(screen.getByText(/future_issue/)).toHaveTextContent("2.000–3.000 秒");
  expect(screen.queryByText("分辨率")).not.toBeInTheDocument();
});

it.each(["facts", "quality"] as const)(
  "includes media details in the %s object tab",
  (tab) => {
    render(
      <ObjectSections
        data={data}
        target={{ ...target, tab }}
        reload={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Audio and video" }),
    ).toBeVisible();
  },
);

it("does not add a media panel to text objects", () => {
  render(
    <ObjectMedia
      data={{ ...data, file }}
      target={{ ...target, id: file.id }}
    />,
  );
  expect(
    screen.queryByRole("region", { name: "Audio and video" }),
  ).not.toBeInTheDocument();
});
