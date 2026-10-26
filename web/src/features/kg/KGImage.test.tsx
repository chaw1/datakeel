import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { cedar, kgProfile, kgSchema } from "../../test/kgFixtures";
import {
  imageExplanation,
  imagePlan,
  imageRef,
  imageRun,
  transcriptRef,
} from "../../test/kgImageFixtures";

import { KGApprovalEstimate } from "./KGApprovalEstimate";
import { KGEntityDrawer } from "./KGEntityDrawer";
import { KGExtractionForm } from "./KGExtractionForm";
import { KGRelationDrawer } from "./KGRelationDrawer";
import { KGReports } from "./KGReports";

it("renders every image region beside highlighted transcript evidence and endpoints", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(imageExplanation))),
    ),
  );
  render(<KGRelationDrawer assertionId="image-relation" onClose={vi.fn()} />);
  expect(
    await screen.findByRole("img", { name: "diagram.png" }),
  ).toHaveAttribute("src", imageExplanation.sources[0].image_url);
  const boxes = screen.getAllByRole("img", { name: /Image evidence region/ });
  expect(boxes).toHaveLength(2);
  expect(boxes[0]).toHaveStyle({
    left: "5%",
    top: "10%",
    width: "40%",
    height: "20%",
  });
  expect(boxes[1]).toHaveStyle({
    left: "55%",
    top: "50%",
    width: "40%",
    height: "30%",
  });
  expect(boxes[0].style.borderColor).not.toBe(boxes[1].style.borderColor);
  expect(
    document.querySelector('[data-anchor-number="1,2"] mark'),
  ).toHaveTextContent("Cedar");
  expect(
    document.querySelector('[data-anchor-number="1,3"] mark'),
  ).toHaveTextContent("Reed");
  expect(screen.getByText(/recorded-vision-model/)).toBeVisible();
  expect(screen.getByText(/recorded-model/)).toBeVisible();
});

it("keeps the original image visible when OCR could not locate evidence", async () => {
  const unresolved = {
    ...imageExplanation,
    relation: {
      ...imageExplanation.relation,
      image_located: false,
      assertion: {
        ...imageExplanation.relation.assertion,
        verification: "needs_review",
        anchors: imageExplanation.relation.assertion.anchors.filter(
          (anchor) => anchor.asset_ref.asset_id !== imageRef.asset_id,
        ),
        verification_detail: {
          ...imageExplanation.relation.assertion.verification_detail,
          issues: [{ code: "image_unlocated" }],
        },
      },
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(unresolved)))),
  );
  render(<KGRelationDrawer assertionId="unlocated-image" onClose={vi.fn()} />);
  expect(await screen.findByRole("img", { name: "diagram.png" })).toBeVisible();
  expect(
    screen.getAllByText("Not located on image; review required.").length,
  ).toBeGreaterThan(0);
  expect(
    screen.queryByRole("img", { name: /Image evidence region/ }),
  ).not.toBeInTheDocument();
  expect(document.querySelectorAll("mark").length).toBeGreaterThan(0);
});

it("uses transcript anchor revision for entity source requests", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(imageExplanation.sources[1]))),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <KGEntityDrawer
      entity={{
        ...cedar,
        mentions: [
          {
            ...cedar.mentions[0],
            anchors: imageExplanation.relation.assertion.anchors.filter(
              (anchor) => anchor.asset_ref.asset_id === transcriptRef.asset_id,
            ),
          },
        ],
      }}
      versionId="dataset-version"
      onClose={vi.fn()}
    />,
  );
  await screen.findByText("diagram.png transcript · Transcript");
  expect(fetch).toHaveBeenCalledWith(
    `/api/kg/sources/transcript-1?version_id=${transcriptRef.version}`,
    expect.anything(),
  );
});

it("shows both outbound stages and the pre-transcription upper-bound basis", () => {
  render(<KGApprovalEstimate plan={imagePlan} />);
  const estimate = screen.getByRole("region", {
    name: "Image transcription estimate",
  });
  expect(
    within(estimate).getByText("Images").nextElementSibling,
  ).toHaveTextContent("2");
  expect(
    within(estimate).getByText("Estimated image tokens").nextElementSibling,
  ).toHaveTextContent("260");
  expect(within(estimate).getByText("vision.example.com")).toBeVisible();
  expect(within(estimate).getByText("Unknown")).toBeVisible();
  expect(screen.getByText("model.example.com")).toBeVisible();
  expect(
    screen.getByText("Input estimated from the transcription output limit."),
  ).toBeVisible();
});

it("shows routes, cached transcriptions and clearly labelled failures", async () => {
  render(<KGReports runs={[imageRun]} />);
  await userEvent
    .setup()
    .click(screen.getByText(/replay-demo/, { selector: "summary span" }));
  expect(screen.getByText("replay / vlm")).toBeVisible();
  expect(screen.getByText("Reused transcription")).toBeVisible();
  expect(screen.getByText("scripted-truncated.png")).toBeVisible();
  expect(screen.getByText("truncated")).toBeVisible();
  expect(
    screen.getByText("Unlocated image relations").nextElementSibling,
  ).toHaveTextContent("1");
});

it("localizes image and handwriting review reasons in Chinese", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  const value = {
    ...imageExplanation,
    relation: {
      ...imageExplanation.relation,
      image_located: false,
      assertion: {
        ...imageExplanation.relation.assertion,
        verification_detail: {
          ...imageExplanation.relation.assertion.verification_detail,
          issues: [{ code: "image_unlocated" }, { code: "handwriting_name" }],
        },
      },
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(value)))),
  );
  render(
    <I18nProvider>
      <KGRelationDrawer assertionId="image" onClose={vi.fn()} />
    </I18nProvider>,
  );
  expect(await screen.findByText("手写人名需复核。")).toBeVisible();
  expect(
    screen.getAllByText("图上未定位，需人工复核。").length,
  ).toBeGreaterThan(0);
});

it("freezes the selected transcription profile without executing an external plan", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(imagePlan))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <KGExtractionForm
      datasetId="images"
      versionId="image-version"
      schemas={[kgSchema]}
      profiles={[kgProfile]}
      transcriptionProfiles={[
        {
          id: "vision",
          backend: "vlm",
          mode: "vlm",
          model: "vision-model",
          interface: "openai",
          base_url: "https://vision.example.com/v1",
          prompt_version: "image-transcription-v1",
          coordinate_space: "pixel",
          coordinate_min_median_iou: 0.3,
          max_output_tokens: 4096,
          timeout_seconds: 120,
          request_parameters: {},
          ocr_model_version: "rapidocr-3.10.0-defaults",
        },
      ]}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByText("Prepare graph extraction", { selector: "summary" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Image transcription profile"),
    "vision",
  );
  await user.click(
    screen.getByRole("button", { name: "Prepare graph extraction" }),
  );
  await screen.findByText("vision.example.com");
  expect(screen.getByLabelText("Image transcription profile")).toBeDisabled();
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_kg_extraction/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: "images",
        version_id: "image-version",
        schema_id: "business",
        profile_id: "replay-demo",
        transcription_profile_id: "vision",
      }),
    }),
  );
});

it("keeps merged image regions attached to their own original source", async () => {
  const secondRef = { ...imageRef, asset_id: "second-image" };
  const secondAnchor = {
    ...imageExplanation.relation.assertion.anchors.at(-1),
    asset_ref: secondRef,
  };
  const merged = {
    ...imageExplanation,
    relation: {
      ...imageExplanation.relation,
      assertion: {
        ...imageExplanation.relation.assertion,
        anchors: [...imageExplanation.relation.assertion.anchors, secondAnchor],
      },
    },
    sources: [
      ...imageExplanation.sources,
      {
        ...imageExplanation.sources[0],
        asset_ref: secondRef,
        filename: "second.png",
        image_url: "/second-image",
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(merged)))),
  );
  render(<KGRelationDrawer assertionId="merged-images" onClose={vi.fn()} />);
  await screen.findByRole("img", { name: "second.png" });
  const sections = document.querySelectorAll(".kg-image-source");
  expect(sections).toHaveLength(2);
  expect(sections[0].querySelectorAll(".kg-image-region")).toHaveLength(2);
  expect(sections[1].querySelectorAll(".kg-image-region")).toHaveLength(1);
});
