import "./globals.css";

export const metadata = {
  title: "ListingPilot · Master Catalogue & Marketplace Listing Automation",
  description: "One master product sheet into complete, rule-checked listings on Amazon, Flipkart and Meesho.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>{children}</body>
    </html>
  );
}
