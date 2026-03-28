export const metadata = {
  title: "HashtagCity - AI Video Analyzer",
  description: "Upload short videos and get AI-generated titles and hashtags",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
