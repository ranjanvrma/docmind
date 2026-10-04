import { ArrowRight, FileUp } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router";

import { HeroVisual } from "@/components/3d/HeroVisual";
import { fadeUp, stagger } from "@/components/animations/motion";
import { Spotlight } from "@/components/effects/Background";
import { Button } from "@/components/ui/button";
import { Badge, StatusDot } from "@/components/ui/primitives";

export function Hero({ onUpload }: { onUpload: () => void }) {
  return (
    <section className="relative grid items-center gap-8 overflow-x-clip pb-10 pt-4 md:grid-cols-[1.05fr_1fr] md:pt-10 lg:gap-4">
      <Spotlight className="-left-[30%] -top-[60%]" />
      <motion.div variants={stagger(0.09)} initial="hidden" animate="show" className="relative z-10">
        <motion.div variants={fadeUp}>
          <Badge tone="accent" className="mb-6">
            <StatusDot tone="success" /> Retrieval-augmented document intelligence
          </Badge>
        </motion.div>
        <motion.h1 variants={fadeUp} className="text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-[3.6rem]">
          Understand your documents, <span className="text-gradient">semantically.</span>
        </motion.h1>
        <motion.p variants={fadeUp} className="mt-5 max-w-lg text-base leading-relaxed text-fg-muted sm:text-lg">
          Upload documents, search their meaning, and ask grounded questions with source-level citations.
        </motion.p>
        <motion.div variants={fadeUp} className="mt-8 flex flex-wrap gap-3">
          <Button variant="primary" size="lg" shimmer onClick={onUpload}>
            <FileUp /> Upload documents
          </Button>
          <Button variant="glass" size="lg" asChild>
            <Link to="/documents">
              Explore documents <ArrowRight />
            </Link>
          </Button>
        </motion.div>
        <motion.dl variants={fadeUp} className="mt-10 grid max-w-md grid-cols-3 gap-4 border-t border-line pt-6 text-xs">
          {[
            ["Extraction", "Page-level"],
            ["Search", "Semantic"],
            ["Answers", "Cited"],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-fg-faint">{k}</dt>
              <dd className="mt-1 font-medium text-fg">{v}</dd>
            </div>
          ))}
        </motion.dl>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1, transition: { duration: 1.1, ease: [0.22, 1, 0.36, 1], delay: 0.15 } }}
        className="relative z-0 h-[340px] sm:h-[420px] md:h-[520px]"
      >
        <HeroVisual />
      </motion.div>
    </section>
  );
}
