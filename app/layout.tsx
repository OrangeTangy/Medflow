import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Medflow · Presence & Activity",
  description:
    "Hospital presence, thoughtfully connected. A secure workspace for staff attendance and activity reporting.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Medflow" },
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#087f75",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
