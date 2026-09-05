"use client";

import { useEffect, useState } from "react";

const content = {
  privacy: {
    eyebrow: "Privacy notice",
    title: "Privacy, with care.",
    intro:
      "EduTrace is designed to minimise data, separate identity from model features, and keep school decisions with authorised people.",
    sections: [
      [
        "What matters",
        "Schools remain responsible for lawful notices, access decisions, retention, and appropriate safeguarding practice. EduTrace does not diagnose learners or make disciplinary decisions. Student information is access-controlled and model requests use pseudonymous keys where possible.",
      ],
      [
        "Before production use",
        "This notice is product guidance, not legal advice. A qualified privacy professional should review the final policy and processing arrangements for the school and Ghanaian context before real learner data is processed.",
      ],
    ],
  },
  terms: {
    eyebrow: "Terms of use",
    title: "Use insight responsibly.",
    intro:
      "EduTrace provides decision support for authorised school staff. It does not guarantee outcomes, diagnose medical or psychological conditions, or replace professional judgement.",
    sections: [
      [
        "Shared responsibilities",
        "Schools must use the service lawfully, protect account access, review recommendations with appropriate context, and follow safeguarding obligations. Users must not use the service to label, punish, exclude, or make irreversible decisions about learners.",
      ],
      [
        "Service limitations",
        "Model availability, accuracy, SMS delivery, and generated recommendations may vary. Production scoring requires an explicitly approved model. Demo records are fictional and must never be treated as evidence about real learners.",
      ],
    ],
  },
};

export default function LegalModal({ type }) {
  const [open, setOpen] = useState(false);
  const page = content[type];

  useEffect(() => {
    if (!open) return undefined;
    const closeOnEscape = (event) => event.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", closeOnEscape);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        className="legal-trigger"
        type="button"
        onClick={() => setOpen(true)}
      >
        {page.eyebrow.replace(" notice", "")}
      </button>
      {open && (
        <div
          className="legal-backdrop"
          role="presentation"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setOpen(false)
          }
        >
          <section
            className="legal-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${type}-modal-title`}
          >
            <button
              className="legal-close"
              type="button"
              aria-label="Close legal information"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
            <div className="eyebrow">{page.eyebrow}</div>
            <h2 id={`${type}-modal-title`}>{page.title}</h2>
            <p className="legal-intro">{page.intro}</p>
            {page.sections.map(([heading, body]) => (
              <div className="legal-section" key={heading}>
                <h3>{heading}</h3>
                <p>{body}</p>
              </div>
            ))}
          </section>
        </div>
      )}
    </>
  );
}
