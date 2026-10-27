import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { dataset, file, version } from "../../test/fixtures";

import { ObjectPointcloud } from "./ObjectPointcloud";
import { ObjectSections } from "./ObjectSections";
import { objectData } from "./testFixtures";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

const pointcloud = {
  ...objectData,
  file: {
    ...file,
    filename: "room.ply",
    modality: "pointcloud",
    metadata: {
      pointcloud_probe: {
        format: "ply",
        encoding: "binary_little_endian",
        point_count: 10000,
        fields: ["x", "y", "z", "intensity"],
        bounding_box: { min: [-4.125, -2, 0], max: [4, 3, 2.5] },
        density: 98.462,
        nan_count: 25,
        inf_count: 4,
        invalid_count: 29,
        invalid_ratio: 0.0029,
        outlier_ratio: 0.12,
        outlier_sample_count: 8192,
        unit_suspected: true,
        unit_reason: "Coordinate extent is consistent with millimeters.",
      },
      pointcloud_preview: {
        artifact_id: "preview-1",
        filename: "room-preview.png",
        width: 640,
        height: 640,
        path: "https://example.invalid/untrusted.png",
      },
    },
  },
} satisfies ObjectData;
const target: ObjectTarget = {
  kind: "file",
  id: file.id,
  datasetId: dataset.id,
  tab: "facts",
};

it("shows point cloud inspection in the existing file facts and quality views", () => {
  const props = { data: pointcloud, target, reload: vi.fn(), onOpen: vi.fn() };
  const { rerender } = render(<ObjectSections {...props} />);
  const inspection = screen.getByRole("region", {
    name: "Point cloud inspection",
  });
  expect(within(inspection).getByText("10,000")).toBeVisible();
  expect(within(inspection).getByText("x, y, z, intensity")).toBeVisible();
  expect(within(inspection).getByText("-4.125, -2, 0")).toBeVisible();
  expect(within(inspection).getByText("4, 3, 2.5")).toBeVisible();
  expect(within(inspection).getByText("0.29%")).toBeVisible();
  expect(within(inspection).getByText("12%")).toBeVisible();
  expect(within(inspection).getByText("8,192")).toBeVisible();
  expect(within(inspection).getByText("Suspected unit mismatch")).toBeVisible();
  expect(
    within(inspection).getByText(/consistent with millimeters/),
  ).toBeVisible();
  rerender(
    <ObjectSections {...props} target={{ ...target, tab: "quality" }} />,
  );
  expect(screen.getByRole("region", { name: "Quality score" })).toBeVisible();
  expect(
    screen.getByRole("region", { name: "Point cloud inspection" }),
  ).toBeVisible();
});

it("pins the same-origin PNG to the selected immutable source version", () => {
  render(
    <ObjectPointcloud
      data={pointcloud}
      target={{ ...target, versionId: "version with/slash" }}
    />,
  );
  expect(screen.getByRole("img")).toHaveAttribute(
    "src",
    `/api/datasets/${dataset.id}/files/${file.id}/pointcloud-preview?version=version+with%2Fslash`,
  );
  expect(screen.getByRole("img")).toHaveAccessibleName(
    "Top-down point cloud preview of room.ply",
  );
});

it("uses the loaded source version and safely encodes identifiers", () => {
  render(
    <ObjectPointcloud
      data={{
        ...pointcloud,
        dataset: { ...dataset, id: "room/scan" },
        file: { ...pointcloud.file, id: "file/scan" },
        version,
      }}
      target={target}
    />,
  );
  expect(screen.getByRole("img")).toHaveAttribute(
    "src",
    `/api/datasets/room%2Fscan/files/file%2Fscan/pointcloud-preview?version=${version.id}`,
  );
});

it("keeps the original file route when no version was selected", () => {
  render(<ObjectPointcloud data={pointcloud} target={target} />);
  expect(screen.getByRole("img")).toHaveAttribute(
    "src",
    `/api/datasets/${dataset.id}/files/${file.id}/pointcloud-preview`,
  );
});

it("shows a readable error after PNG loading fails and can show another source", () => {
  const { rerender } = render(
    <ObjectPointcloud data={pointcloud} target={target} />,
  );
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByRole("status")).toHaveTextContent(
    "The point cloud preview could not be loaded.",
  );
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  rerender(
    <ObjectPointcloud
      data={pointcloud}
      target={{ ...target, versionId: version.id }}
    />,
  );
  expect(screen.getByRole("img")).toBeVisible();
});

it("explains ungenerated previews without requesting an image", () => {
  render(
    <ObjectPointcloud
      data={{
        ...pointcloud,
        file: {
          ...pointcloud.file,
          metadata: {
            pointcloud_probe: { point_count: 0, bounding_box: null },
          },
        },
      }}
      target={target}
    />,
  );
  expect(screen.getByText("0", { exact: true })).toBeVisible();
  expect(screen.getByText(/No preview has been generated/)).toBeVisible();
  expect(screen.getAllByText("Not recorded").length).toBeGreaterThan(0);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("does not add point cloud details to files without a probe", () => {
  const { container } = render(
    <ObjectPointcloud data={{ ...objectData, file }} target={target} />,
  );
  expect(container).toBeEmptyDOMElement();
});

it("preserves small nonzero densities instead of rounding them to zero", () => {
  render(
    <ObjectPointcloud
      data={{
        ...pointcloud,
        file: {
          ...pointcloud.file,
          metadata: { pointcloud_probe: { density: 0.00000001 } },
        },
      }}
      target={target}
    />,
  );
  expect(screen.getByText("0.00000001", { exact: true })).toBeVisible();
});

it("preserves exact large point counts without significant-digit rounding", () => {
  render(
    <ObjectPointcloud
      data={{
        ...pointcloud,
        file: {
          ...pointcloud.file,
          metadata: {
            pointcloud_probe: {
              point_count: 9_876_543,
              nan_count: 1_234_567,
              inf_count: 2_345_679,
              outlier_sample_count: 8_192,
            },
          },
        },
      }}
      target={target}
    />,
  );
  for (const count of ["9,876,543", "1,234,567", "2,345,679", "8,192"])
    expect(screen.getByText(count, { exact: true })).toBeVisible();
  expect(
    screen.queryByText("9,876,540", { exact: true }),
  ).not.toBeInTheDocument();
});

it.each([
  [
    "extent_exceeds_expected_maximum_possible_millimeters",
    "millimeter units are possible",
  ],
  ["batch_extent_ratio_possible_unit_mismatch", "mixed units are possible"],
])(
  "explains the unit warning %s in readable language",
  (reason, description) => {
    render(
      <ObjectPointcloud
        data={{
          ...pointcloud,
          file: {
            ...pointcloud.file,
            metadata: { pointcloud_probe: { unit_reason: reason } },
          },
        }}
        target={target}
      />,
    );
    expect(screen.getByText(new RegExp(description))).toBeVisible();
    expect(screen.queryByText(reason, { exact: true })).not.toBeInTheDocument();
  },
);

it("localizes point cloud labels and reports no detected unit mismatch", () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <ObjectPointcloud
        data={{
          ...pointcloud,
          file: {
            ...pointcloud.file,
            metadata: { pointcloud_probe: { unit_suspected: false } },
          },
        }}
        target={target}
      />
    </I18nContext.Provider>,
  );
  expect(screen.getByRole("heading", { name: "点云探测" })).toBeVisible();
  expect(screen.getByText("未发现单位错配")).toBeVisible();
  expect(screen.getByText("最小坐标（x、y、z）")).toBeVisible();
  expect(screen.getByText(/尚未生成预览/)).toBeVisible();
});
