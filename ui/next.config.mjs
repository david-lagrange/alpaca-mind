/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output produces a self-contained server bundle so the
  // deployment's service manager can run the app directly with Node.
  output: "standalone",
  experimental: {
    // better-sqlite3 is a native module; it must be required at runtime
    // rather than bundled by the compiler.
    serverComponentsExternalPackages: ["better-sqlite3"],
  },
};

export default nextConfig;
