// utils/clipboard 单测：主路径 + execCommand 降级 + 假成功防护（2026-10-11 修复点锁定）
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { copyText } from "@/utils/clipboard";

describe("copyText", () => {
  let writeText: ReturnType<typeof vi.fn>;
  let execCommand: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeText = vi.fn();
    execCommand = vi.fn();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true
    });
    (document as unknown as { execCommand: unknown }).execCommand =
      execCommand;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("Clipboard API 成功 → true，不走降级", async () => {
    writeText.mockResolvedValue(undefined);
    await expect(copyText("hello")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
    expect(execCommand).not.toHaveBeenCalled();
  });

  it("Clipboard API 被拦截 → 降级 execCommand 成功返回 true", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    execCommand.mockReturnValue(true);
    await expect(copyText("hello")).resolves.toBe(true);
    expect(execCommand).toHaveBeenCalledWith("copy");
  });

  it("降级 execCommand 返回 false（假成功防护）→ false", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    execCommand.mockReturnValue(false);
    await expect(copyText("hello")).resolves.toBe(false);
  });

  it("降级 execCommand 抛异常 → false，且临时 textarea 被清理", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    execCommand.mockImplementation(() => {
      throw new Error("boom");
    });
    await expect(copyText("hello")).resolves.toBe(false);
    expect(document.querySelectorAll("textarea")).toHaveLength(0);
  });
});
