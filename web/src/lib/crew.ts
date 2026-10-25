import {
  BookOpen,
  ClipboardList,
  Code2,
  FlaskConical,
  GitBranch,
  ShieldCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";

/** One pipeline stage, described for someone who has never seen CodeCrew. */
export interface Step {
  id: string;
  label: string;
  agent: string;
  /** What happens in this stage, in one plain sentence. */
  plain: string;
  /** Shown while the stage is running. */
  doing: string;
  icon: LucideIcon;
  tone: string;
}

export const STEP: Record<string, Step> = {
  planning: {
    id: "planning",
    label: "Plan",
    agent: "Planner",
    plain: "Turns your idea into a precise plan: which files, which functions, and what counts as done.",
    doing: "Writing the plan",
    icon: ClipboardList,
    tone: "#6ca8ff",
  },
  triage: {
    id: "triage",
    label: "Understand change",
    agent: "Orchestrator",
    plain: "Works out the smallest set of files your change needs, so nothing else breaks.",
    doing: "Deciding what to change",
    icon: GitBranch,
    tone: "#6ca8ff",
  },
  testing: {
    id: "testing",
    label: "Write tests",
    agent: "Test Author",
    plain: "Writes tests from the plan before any code exists, so the tests can't be bent to fit buggy code.",
    doing: "Writing the tests",
    icon: FlaskConical,
    tone: "#e8ae79",
  },
  coding: {
    id: "coding",
    label: "Write code",
    agent: "Coder",
    plain: "Writes the actual code, aiming to pass every test.",
    doing: "Writing the code",
    icon: Code2,
    tone: "#8bd49d",
  },
  verifying: {
    id: "verifying",
    label: "Check",
    agent: "Verifier",
    plain: "Really runs the tests and code checkers. No AI guessing: pass means it actually passed.",
    doing: "Running the tests and checks",
    icon: ShieldCheck,
    tone: "#c39bff",
  },
  debugging: {
    id: "debugging",
    label: "Fix",
    agent: "Debugger",
    plain: "Finds why a check failed and fixes it. A fix that makes things worse is undone automatically.",
    doing: "Fixing what failed",
    icon: Wrench,
    tone: "#f78c8c",
  },
  documenting: {
    id: "documenting",
    label: "Document",
    agent: "Reviewer",
    plain: "Adds explanations to the code and writes a README telling you how to use it.",
    doing: "Writing the docs",
    icon: BookOpen,
    tone: "#5eead4",
  },
};

export const BUILD_STEPS = ["planning", "testing", "coding", "verifying", "debugging", "documenting"];
export const ITERATE_STEPS = ["triage", "testing", "coding", "verifying", "debugging", "documenting"];

/** Colour per agent name as it appears in the activity stream. */
export const AGENT_TONE: Record<string, string> = {
  Orchestrator: "#9d8dfa",
  Planner: "#6ca8ff",
  "Test Author": "#e8ae79",
  "Code Generation": "#8bd49d",
  Coder: "#8bd49d",
  Verifier: "#c39bff",
  Debugging: "#f78c8c",
  Debugger: "#f78c8c",
  Review: "#5eead4",
  Reviewer: "#5eead4",
  LLM: "#858b98",
};

export const EXAMPLES = [
  {
    title: "Roman numerals",
    hint: "Python · logic + tests",
    prompt: "A Python module roman.py with to_roman(n) and from_roman(s) for 1..3999 that rejects invalid numerals",
  },
  {
    title: "Tip calculator",
    hint: "Web page",
    prompt: "A tip calculator web page: bill, tip % and number of people, showing per-person totals rounded to cents",
  },
  {
    title: "To-do list app",
    hint: "Python · command line",
    prompt: "A CLI todo app in Python that stores tasks in a JSON file with add, list, done and delete commands",
  },
  {
    title: "LRU cache",
    hint: "Python · data structure",
    prompt: "An LRU cache class in Python with get/put and a configurable capacity",
  },
];
