import "./globals.css";

export const metadata = {
  title: "EduTrace | Understand. Support. Follow up.",
  description:
    "A human-centred early warning and student support platform for schools.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
