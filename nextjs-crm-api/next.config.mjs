/** @type {import('next').NextConfig} */
const nextConfig = {
  // native/wasm DB drivers must not be bundled
  serverExternalPackages: ["pg", "@electric-sql/pglite"],
};
export default nextConfig;
