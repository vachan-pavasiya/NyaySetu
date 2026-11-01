# NyaySetu Frontend

The modern editorial and gazette-style web interface for **NyaySetu: Court-Order Compliance Radar**. Built with React, Vite, TypeScript, and Tailwind CSS.

## Architecture

- **Principal Register (Dashboard)**: Real-time compliance health, top departments with pending directives, upcoming deadline windows, and pipeline audit logs.
- **Compliance Ledger**: Paginated, filterable table of operative judicial directions with full search by department, compliance status, and date range.
- **Law Report & Judgment View**: Detailed judgment inspector with side-by-side operative text segmentation, verbatim quote verification offsets, and confidence indicators.
- **Case Progression & Timeline**: Interactive timeline visualizing original writ petitions linked to subsequent contempt proceedings (`CPAN` in `WPA`) and compliance filings.
- **Deadline Calendar**: Monthly calendar view of approaching compliance window closures and service lag buffers.
- **Evaluation Benchmarks**: Live accuracy and fidelity metrics against hand-labelled ground truth.

## Development

```bash
# Install dependencies
npm install

# Run Vite dev server
npm run dev

# Build production bundle
npm run build
```

## Environment Configuration

Configure `VITE_API_URL` in `.env` or during deployment:

```bash
VITE_API_URL=https://nyaysetu-backend-dfr6.onrender.com
```
