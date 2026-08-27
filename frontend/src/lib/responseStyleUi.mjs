export const RESPONSE_STYLES = [
  {
    id: "concise",
    title: "Ngắn gọn",
    description: "Tập trung vào kết quả chính và hành động cần thiết, ít thuật ngữ.",
  },
  {
    id: "simple",
    title: "Dễ hiểu",
    description: "Giải thích nhẹ nhàng, dễ tiếp cận, có diễn giải từ ngữ y khoa.",
  },
  {
    id: "detailed",
    title: "Chi tiết",
    description: "Cung cấp thêm bối cảnh giáo dục và phân tích sâu hơn.",
  },
];

export function getResponseStyleLabel(style) {
  const found = RESPONSE_STYLES.find((item) => item.id === style);
  return found ? found.title : "Dễ hiểu";
}

export function isValidResponseStyle(style) {
  return ["concise", "simple", "detailed"].includes(style);
}
