// Renders a long-form guide from the structured blocks in content/guides.js.

function inline(text) {
  // split on **bold** and wrap odd segments
  return text.split("**").map((seg, i) =>
    i % 2 === 1 ? <strong key={i}>{seg}</strong> : <span key={i}>{seg}</span>
  );
}

export default function GuidePage({ guide, onNav, onSearchCta }) {
  return (
    <main className="page guide">
      <div className="wrap narrow">
        <button className="guide-back" onClick={() => onNav("/")}>← Back to search</button>
        <h1>{guide.h1}</h1>
        <div className="prose">
          {guide.blocks.map((b, i) => {
            if (b.h2) return <h2 key={i}>{b.h2}</h2>;
            if (b.h3) return <h3 key={i}>{b.h3}</h3>;
            if (b.p) return <p key={i}>{inline(b.p)}</p>;
            if (b.note) return <p key={i} className="prose-note">{inline(b.note)}</p>;
            if (b.ul) return (
              <ul key={i}>{b.ul.map((li, j) => <li key={j}>{inline(li)}</li>)}</ul>
            );
            if (b.table) return (
              <div className="prose-table-wrap" key={i}>
                <table className="prose-table">
                  <thead><tr>{b.table.head.map((h, j) => <th key={j}>{h}</th>)}</tr></thead>
                  <tbody>
                    {b.table.rows.map((row, r) => (
                      <tr key={r}>{row.map((c, k) => <td key={k} className={k === 0 ? "rowhead" : ""}>{c}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
            return null;
          })}
        </div>

        <div className="guide-cta">
          <h3>See which providers are active in your area</h3>
          <p>Enter your property postcode to find care and housing providers who hold contracts with your council.</p>
          <button className="btn btn-primary" onClick={onSearchCta}>Find providers near you</button>
        </div>
      </div>
    </main>
  );
}
