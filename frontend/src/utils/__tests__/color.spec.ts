import { describe, expect, it } from "vitest";
import { hexToRgba, normalizeHex } from "../color";

describe("normalizeHex", () => {
  it("补全三位简写为六位", () => {
    expect(normalizeHex("#abc")).toBe("#aabbcc");
  });

  it("保留六位格式并统一 # 前缀", () => {
    expect(normalizeHex("3b82f6")).toBe("#3b82f6");
    expect(normalizeHex("#3B82F6")).toBe("#3B82F6");
  });

  it("非法输入原样返回（交由 CSS 兜底）", () => {
    expect(normalizeHex("red")).toBe("red");
    expect(normalizeHex("#12345")).toBe("#12345");
  });
});

describe("hexToRgba", () => {
  it("六位 hex 转 rgba", () => {
    expect(hexToRgba("#3b82f6", 0.5)).toBe("rgba(59, 130, 246, 0.5)");
  });

  it("三位简写同样支持", () => {
    expect(hexToRgba("#fff", 1)).toBe("rgba(255, 255, 255, 1)");
  });

  it("透明度收敛到 [0,1]", () => {
    expect(hexToRgba("#000000", -1)).toBe("rgba(0, 0, 0, 0)");
    expect(hexToRgba("#000000", 2)).toBe("rgba(0, 0, 0, 1)");
    expect(hexToRgba("#000000", Number.NaN)).toBe("rgba(0, 0, 0, 1)");
  });

  it("非法颜色原样返回", () => {
    expect(hexToRgba("oops", 0.5)).toBe("oops");
  });
});
