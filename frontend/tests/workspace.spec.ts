import { expect, test, type Page } from "@playwright/test";

async function register(page: Page) {
  await page.goto("/");
  await page.getByLabel("Your name").fill("Alex Builder");
  await page
    .getByLabel("Email address")
    .fill(
      `builder-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
    );
  await page
    .getByLabel("Password", { exact: true })
    .fill("local-test-password-123");
  await page.getByRole("button", { name: "Create your workspace" }).click();
  await expect(
    page.getByRole("heading", { name: /A better website/ }),
  ).toBeVisible();
}

test("a complete offline build persists drafts, evaluation and downloadable HTML", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await register(page);
  await page
    .getByRole("button", { name: "Design studio", exact: true })
    .click();
  await page.getByRole("button", { name: "Walkthrough", exact: true }).click();
  await page.getByRole("button", { name: "Try the walkthrough" }).click();
  await expect(
    page.getByRole("button", { name: "Run another iteration cycle" }),
  ).toBeEnabled();
  await expect(page.locator(".iteration-strip button")).toHaveCount(5);
  await expect(page.getByTitle("Generated website preview")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/workspace-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Evaluation", exact: true }).click();
  await expect(page.getByText("Quality you can inspect.")).toBeVisible();
  await expect(
    page.getByText(
      "Offline walkthrough: the design rubric below is simulated.",
      { exact: false },
    ),
  ).toBeVisible();
  await page.getByText(/deterministic checks ·/).click();
  await expect(
    page.getByText("Semantic Structure", { exact: true }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download HTML", exact: true })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("forma-studio.html");
  await page.reload();
  await page.getByRole("button", { name: /My projects/ }).click();
  await page.getByRole("button", { name: /Forma Studio/ }).click();
  await expect(page.locator(".iteration-strip button")).toHaveCount(5);
  await expect(page.getByTitle("Generated website preview")).toBeVisible();
  await page.getByRole("button", { name: "mobile preview" }).click();
  await expect(page.locator(".iframe-container")).toHaveClass(/mobile/);
  expect(errors).toEqual([]);
});

test("profile changes and rollback keep a visible version history", async ({
  page,
}) => {
  await register(page);
  await page
    .getByRole("button", { name: "Evaluation profiles", exact: true })
    .click();
  await page.getByRole("button", { name: "Edit criteria" }).click();
  await page
    .getByLabel("Editable criteria")
    .fill("- Prefer warm palettes\n- Reward accessible, responsive layouts");
  await page.getByRole("button", { name: "Save criteria" }).click();
  await expect(page.getByText("SAVED CRITERIA DIFF")).toBeVisible();
  await page.getByText(/Version history ·/).click();
  await page.getByRole("button", { name: /v1.*Created profile/ }).click();
  await page
    .getByRole("button", { name: "Restore v1 as a new version" })
    .click();
  await expect(page.getByText("Version history · 3 versions")).toBeVisible();
  await page.getByRole("button", { name: "New profile", exact: true }).click();
  await page.getByLabel("Profile name").fill("Editorial");
  await page.getByRole("button", { name: "Save criteria" }).click();
  await expect(
    page.getByRole("heading", { name: "Editorial", exact: true }),
  ).toBeVisible();
});

test("mobile workspace stays within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await register(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/workspace-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /My projects/ }).click();
  await expect(
    page.getByRole("heading", { name: /A place for your projects/ }),
  ).toBeVisible();
});
