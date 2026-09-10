import WorkbenchTabs from "@/components/workbench/workbench-tabs";

export default function Home() {
  return (
    <div className="mx-auto max-w-2xl px-6 pb-12 pt-16">
      <h1 className="sr-only">工作台</h1>
      <WorkbenchTabs />
    </div>
  );
}
