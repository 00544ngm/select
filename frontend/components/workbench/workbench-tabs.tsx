"use client";

import { useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { Search, Sparkles, Scale } from "lucide-react";
import HypothesisForm from "./hypothesis-form";
import JudgmentForm from "./judgment-form";
import SearchForm from "./search-form";

interface WorkbenchTabsProps {
  isSubmitting?: boolean;
}

const TAB_META = [
  { value: "hypothesis", label: "假设分析", icon: Sparkles },
  { value: "judgment", label: "对比审判", icon: Scale },
  { value: "search", label: "搜索商品", icon: Search },
];

const TAB_HINTS: Record<string, string> = {
  hypothesis: "粘贴主品链接，开始分析",
  judgment: "输入 A 品与 B 品链接，审判组合可行性",
  search: "搜索商品，挑选 B 品接力审判",
};

export default function WorkbenchTabs({ isSubmitting }: WorkbenchTabsProps) {
  const [tab, setTab] = useState("hypothesis");
  const [selectedBUrls, setSelectedBUrls] = useState<string[]>([]);

  const handleSelectB = (urls: string[]) => {
    setSelectedBUrls(urls);
    setTab("judgment");
  };

  return (
    <Tabs.Root value={tab} onValueChange={setTab} className="w-full">
      <p className="mb-5 text-center text-base text-muted-foreground">
        {TAB_HINTS[tab]}
      </p>

      <Tabs.List
        className="mx-auto mb-6 flex w-fit gap-1 rounded-full border border-border p-1"
        role="tablist"
      >
        {TAB_META.map(({ value, label, icon: Icon }) => (
          <Tabs.Trigger
            key={value}
            value={value}
            className="flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm text-muted-foreground transition-colors data-[state=active]:bg-foreground data-[state=active]:text-background"
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>

      <div>
        <Tabs.Content
          value="hypothesis"
          forceMount
          className={tab !== "hypothesis" ? "hidden" : ""}
        >
          <HypothesisForm isSubmitting={isSubmitting} />
        </Tabs.Content>
        <Tabs.Content
          value="judgment"
          forceMount
          className={tab !== "judgment" ? "hidden" : ""}
        >
          <JudgmentForm isSubmitting={isSubmitting} defaultBUrls={selectedBUrls} />
        </Tabs.Content>
        <Tabs.Content
          value="search"
          forceMount
          className={tab !== "search" ? "hidden" : ""}
        >
          <SearchForm onSelectB={handleSelectB} />
        </Tabs.Content>
      </div>
    </Tabs.Root>
  );
}
