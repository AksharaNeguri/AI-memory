"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
  useEdgesState,
  useNodesState
} from "@xyflow/react";
import {
  Bell,
  BookOpen,
  Bot,
  Brain,
  Check,
  ChevronRight,
  CircleUserRound,
  CloudUpload,
  Code2,
  FilePlus2,
  FileText,
  FolderOpen,
  Gauge,
  GitFork,
  Globe2,
  Home as HomeIcon,
  KeyRound,
  Link2,
  Loader2,
  Lock,
  Mail,
  Menu,
  MessageSquare,
  Network,
  Plus,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  X
} from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";

type User = {
  id: string;
  email: string;
  full_name: string | null;
};

type DocumentRead = {
  id: string;
  title: string;
  source_type: string;
  source_url: string | null;
  processing_status: string;
  error_message: string | null;
  chunks?: Array<{ id: string; content: string; chunk_index: number }>;
};

type SearchResult = {
  chunk_id: string;
  document_id: string;
  title: string;
  content: string;
  score: number;
};

type GraphNode = {
  id: string;
  labels: string[];
  name: string;
  properties: Record<string, string>;
};

type GraphRelationship = {
  source: string;
  target: string;
  type: string;
  properties: Record<string, string>;
};

type SourceCitation = {
  citation_id: number;
  document_id: string;
  chunk_id: string;
  title: string;
  chunk_index: number;
  source_type: string;
  source_url: string | null;
  quote: string;
  score: number;
};

type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  citations: SourceCitation[];
  grounded: boolean;
};

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: SourceCitation[];
  grounded?: boolean;
};

type View =
  | "Dashboard"
  | "Memories"
  | "Add Memory"
  | "Search"
  | "Ask My Memory"
  | "Knowledge Graph"
  | "Timeline"
  | "Settings"
  | "Conversations";

const navItems: Array<{ label: View; icon: typeof HomeIcon }> = [
  { label: "Dashboard", icon: HomeIcon },
  { label: "Memories", icon: FolderOpen },
  { label: "Add Memory", icon: FilePlus2 },
  { label: "Search", icon: Search },
  { label: "Ask My Memory", icon: Bot },
  { label: "Knowledge Graph", icon: Network },
  { label: "Timeline", icon: BookOpen },
  { label: "Settings", icon: Settings },
  { label: "Conversations", icon: MessageSquare }
];

const graphSeedNodes: Node[] = [
  { id: "python", data: { label: "Python" }, position: { x: 360, y: 180 }, style: graphNodeStyle("#2563eb") },
  { id: "fastapi", data: { label: "FastAPI" }, position: { x: 350, y: 330 }, style: graphNodeStyle("#0891b2") },
  { id: "ml", data: { label: "Machine Learning" }, position: { x: 360, y: 60 }, style: graphNodeStyle("#0f766e") },
  { id: "pandas", data: { label: "Pandas" }, position: { x: 570, y: 160 }, style: graphNodeStyle("#0e7490") },
  { id: "project", data: { label: "Backend Development" }, position: { x: 90, y: 250 }, style: graphNodeStyle("#7c3aed") },
  { id: "api", data: { label: "REST API" }, position: { x: 500, y: 390 }, style: graphNodeStyle("#059669") },
  { id: "http", data: { label: "HTTP" }, position: { x: 350, y: 470 }, style: graphNodeStyle("#1d4ed8") }
];

const graphSeedEdges: Edge[] = [
  { id: "python-fastapi", source: "python", target: "fastapi", animated: true, style: { stroke: "#14f1c8" } },
  { id: "python-ml", source: "python", target: "ml", animated: true, style: { stroke: "#14f1c8" } },
  { id: "python-pandas", source: "python", target: "pandas", animated: true, style: { stroke: "#38bdf8" } },
  { id: "fastapi-api", source: "fastapi", target: "api", animated: true, style: { stroke: "#14f1c8" } },
  { id: "api-http", source: "api", target: "http", animated: true, style: { stroke: "#38bdf8" } },
  { id: "project-python", source: "project", target: "python", animated: true, style: { stroke: "#8b5cf6" } }
];

const sampleTopics = [
  ["Python", "14"],
  ["Machine Learning", "10"],
  ["Java", "8"],
  ["APIs", "7"],
  ["Data Structures", "6"]
];

const sampleTimeline = [
  ["Oct 10, 2024", "Added note", "REST API Basics"],
  ["Oct 8, 2024", "Uploaded", "machine-learning.pdf"],
  ["Oct 5, 2024", "Asked AI", "FastAPI Tutorial"],
  ["Oct 3, 2024", "Added note", "Python Basics"],
  ["Sep 20, 2024", "Uploaded", "Java Programming"]
];

export default function Home() {
  const [email, setEmail] = useState("ada@example.com");
  const [password, setPassword] = useState("correct-horse-battery");
  const [fullName, setFullName] = useState("Ammulu");
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [activeView, setActiveView] = useState<View>("Dashboard");
  const [status, setStatus] = useState("Your memory system is ready.");
  const [documents, setDocuments] = useState<DocumentRead[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [textTitle, setTextTitle] = useState("REST API Basics");
  const [textContent, setTextContent] = useState(
    "REST APIs allow applications to communicate using HTTP methods like GET, POST, PUT, DELETE, and return data formats like JSON or XML."
  );
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [graphQuery, setGraphQuery] = useState("");
  const [relationships, setRelationships] = useState<GraphRelationship[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentRead | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [chatQuestion, setChatQuestion] = useState("What did I learn about APIs last month?");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [processingOpen, setProcessingOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [graphNodes, setGraphNodes, onNodesChange] = useNodesState<Node>(graphSeedNodes);
  const [graphEdges, setGraphEdges, onEdgesChange] = useEdgesState<Edge>(graphSeedEdges);

  const loadDocuments = useCallback(async (activeToken: string) => {
    const items = await api<DocumentRead[]>("/documents", { token: activeToken });
    setDocuments(items);
  }, []);

  const loadMe = useCallback(
    async (activeToken: string) => {
      const profile = await api<User>("/auth/me", { token: activeToken });
      setUser(profile);
      setStatus("Authenticated. Your memory is synced.");
      await loadDocuments(activeToken);
    },
    [loadDocuments]
  );

  useEffect(() => {
    const savedToken = window.localStorage.getItem("ai_memory_token");
    if (savedToken) {
      setToken(savedToken);
      void loadMe(savedToken);
    }
  }, [loadMe]);

  async function submitAuth() {
    setStatus("Working...");
    try {
      if (authMode === "register") {
        await api<User>("/auth/register", {
          method: "POST",
          body: { email, password, full_name: fullName }
        });
      }
      const login = await api<{ access_token: string }>("/auth/login", {
        method: "POST",
        form: { username: email, password }
      });
      window.localStorage.setItem("ai_memory_token", login.access_token);
      setToken(login.access_token);
      await loadMe(login.access_token);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Authentication failed.");
    }
  }

  async function ingestText() {
    if (!token || !textTitle.trim() || !textContent.trim()) return;
    setStatus("Saving note...");
    try {
      const document = await api<DocumentRead>("/documents/text", {
        method: "POST",
        token,
        body: { title: textTitle, content: textContent }
      });
      setStatus(`${document.title} saved to memory.`);
      await loadDocuments(token);
      setActiveView("Memories");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not save note.");
    }
  }

  async function uploadDocument() {
    if (!token || !selectedFile) return;
    setStatus("Processing PDF...");
    setProcessingOpen(true);
    try {
      const form = new FormData();
      form.set("file", selectedFile);
      const document = await api<DocumentRead>("/documents/upload", {
        method: "POST",
        token,
        multipart: form
      });
      setStatus(`${document.title} processed.`);
      await loadDocuments(token);
      setActiveView("Memories");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  async function ingestUrl() {
    if (!token || !url.trim()) return;
    setStatus("Fetching URL...");
    try {
      const document = await api<DocumentRead>("/documents/url", {
        method: "POST",
        token,
        body: { url }
      });
      setStatus(`${document.title} added.`);
      setUrl("");
      await loadDocuments(token);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "URL import failed.");
    }
  }

  async function runSearch(searchValue = query) {
    if (!token || !searchValue.trim()) return;
    setStatus("Searching memory...");
    try {
      const response = await api<{ results: SearchResult[] }>("/search", {
        method: "POST",
        token,
        body: { query: searchValue, hybrid: true, limit: 10 }
      });
      setResults(response.results);
      setActiveView("Search");
      setStatus(`Found ${response.results.length} relevant memories.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Search failed.");
    }
  }

  async function sendChat() {
    if (!token || !chatQuestion.trim() || chatLoading) return;
    const question = chatQuestion.trim();
    setChatLoading(true);
    setChatTurns((turns) => [...turns, { role: "user", content: question }]);
    setChatQuestion("");
    setStatus("Building grounded answer...");
    try {
      const response = await api<ChatResponse>("/chat", {
        method: "POST",
        token,
        body: { message: question, conversation_id: conversationId }
      });
      setConversationId(response.conversation_id);
      setChatTurns((turns) => [
        ...turns,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations,
          grounded: response.grounded
        }
      ]);
      setActiveView("Ask My Memory");
      setStatus(response.grounded ? "Answered with sources." : "No supporting memory found.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Assistant failed.");
      setChatTurns((turns) => turns.filter((turn) => turn.role !== "user" || turn.content !== question));
    } finally {
      setChatLoading(false);
    }
  }

  async function loadGraph() {
    if (!token) return;
    setStatus("Loading graph...");
    try {
      const response = await api<{ nodes: GraphNode[]; relationships: GraphRelationship[] }>(
        `/graph/nodes?q=${encodeURIComponent(graphQuery)}`,
        { token }
      );
      setRelationships(response.relationships);
      if (response.nodes.length) setGraphNodes(toFlowNodes(response.nodes));
      if (response.relationships.length) setGraphEdges(toFlowEdges(response.relationships));
      setActiveView("Knowledge Graph");
      setStatus("Graph loaded.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Graph unavailable.");
    }
  }

  async function extractGraph(documentId: string) {
    if (!token) return;
    setStatus("Extracting knowledge graph...");
    try {
      await api(`/graph/documents/${documentId}/extract`, { method: "POST", token });
      await loadGraph();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Graph extraction failed.");
    }
  }

  async function openDocument(documentId?: string) {
    if (!token || !documentId || documentId.startsWith("mock-")) return;
    try {
      const document = await api<DocumentRead>(`/documents/${documentId}`, { token });
      setSelectedDocument(document);
      setActiveView("Memories");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Document could not be opened.");
    }
  }

  function logout() {
    window.localStorage.removeItem("ai_memory_token");
    setToken(null);
    setUser(null);
    setDocuments([]);
    setChatTurns([]);
    setStatus("Logged out.");
  }

  const displayName = user?.full_name || fullName || "Ammulu";
  const userEmail = user?.email ?? email;
  const memoryCount = Math.max(documents.length, 42);
  const selectedRelationships = useMemo(() => {
    if (!selectedNode) return relationships;
    return relationships.filter((item) => item.source === selectedNode.id || item.target === selectedNode.id);
  }, [relationships, selectedNode]);

  if (!token || !user) {
    return (
      <AuthWebsite
        mode={authMode}
        setMode={setAuthMode}
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        fullName={fullName}
        setFullName={setFullName}
        onSubmit={submitAuth}
        status={status}
      />
    );
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[#07182a] text-slate-100">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(20,241,200,0.12),transparent_28%),radial-gradient(circle_at_85%_15%,rgba(92,124,255,0.14),transparent_26%),linear-gradient(135deg,#09223a,#06111e_42%,#020912)]" />
      <div className="relative flex min-h-screen">
        <aside
          className={`fixed inset-y-0 left-0 z-30 w-64 border-r border-cyan-300/15 bg-[#061321]/95 p-4 shadow-2xl shadow-cyan-950/40 transition-transform lg:static lg:translate-x-0 ${
            mobileNavOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <Sidebar
            activeView={activeView}
            setActiveView={(view) => {
              setActiveView(view);
              setMobileNavOpen(false);
            }}
            userName={displayName}
            onLogout={logout}
          />
        </aside>
        <section className="flex min-w-0 flex-1 flex-col">
          <Topbar
            query={query}
            setQuery={setQuery}
            onSearch={() => void runSearch()}
            onMenu={() => setMobileNavOpen(true)}
            userName={displayName}
          />
          <div className="flex-1 overflow-auto p-4 sm:p-5 lg:p-6">
            <div className="mx-auto max-w-[1440px]">{renderView()}</div>
          </div>
        </section>
      </div>
      {mobileNavOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
    </main>
  );

  function renderView() {
    if (activeView === "Dashboard") {
      return (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold text-white">Good morning, {displayName}</h1>
              <p className="text-sm text-cyan-100/70">Your knowledge, organized and searchable.</p>
            </div>
            <button onClick={() => setActiveView("Add Memory")} className="primary-button">
              <Plus className="h-4 w-4" />
              Add Memory
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard icon={BookOpen} label="Memories" value={String(memoryCount)} />
            <StatCard icon={GitFork} label="Concepts" value="387" tone="sky" />
            <StatCard icon={Network} label="Connections" value="921" tone="violet" />
            <StatCard icon={Gauge} label="Topics" value="28" tone="amber" />
          </div>
          <div className="grid gap-4 xl:grid-cols-[1.45fr_0.9fr_0.85fr]">
            <Panel title="Memory Growth">
              <MiniChart />
            </Panel>
            <Panel title="Top Topics">
              <TopicList />
            </Panel>
            <Panel title="Knowledge Overview">
              <DonutLegend />
            </Panel>
          </div>
          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.9fr_0.8fr]">
            <Panel title="Recent Memories" action="View all">
              <RecentMemories />
            </Panel>
            <Panel title="Quick Actions">
              <div className="grid gap-2">
                <ActionRow icon={FilePlus2} label="Add Note" onClick={() => setActiveView("Add Memory")} />
                <ActionRow icon={Upload} label="Upload PDF" onClick={() => setActiveView("Add Memory")} />
                <ActionRow icon={Bot} label="Ask My Memory" onClick={() => setActiveView("Ask My Memory")} />
                <ActionRow icon={Network} label="Explore Graph" onClick={() => setActiveView("Knowledge Graph")} />
              </div>
            </Panel>
            <Panel title="System Status">
              <p className="rounded-md border border-cyan-300/15 bg-[#07192a] p-3 text-sm text-cyan-100/70">{status}</p>
            </Panel>
          </div>
        </div>
      );
    }

    if (activeView === "Add Memory") {
      return (
        <div className="grid gap-4 xl:grid-cols-[1fr_0.8fr]">
          <section className="space-y-5">
            <SectionHeading title="Add to your memory" subtitle="Save something you learned, read, or created." />
            <div className="grid gap-4 md:grid-cols-3">
              <ChoiceCard icon={FilePlus2} title="Add Note" copy="Write or paste something you want your AI memory to remember." />
              <ChoiceCard icon={CloudUpload} title="Upload PDF" copy="Upload lecture notes, research papers, books, or documents." />
              <ChoiceCard icon={Link2} title="Add URL" copy="Save useful web pages to your memory." />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <ChoiceCard icon={Code2} title="Add Code" copy="Save code snippets and projects." compact />
              <ChoiceCard icon={Globe2} title="YouTube Transcript" copy="Save video transcripts when available." compact />
            </div>
            <Panel title="Create a new note">
              <div className="grid gap-4">
                <Field label="Title">
                  <input value={textTitle} onChange={(event) => setTextTitle(event.target.value)} className="input" />
                </Field>
                <Field label="Content">
                  <textarea
                    value={textContent}
                    onChange={(event) => setTextContent(event.target.value)}
                    className="input min-h-36 resize-none"
                    maxLength={2000}
                  />
                  <p className="text-right text-xs text-cyan-100/45">{textContent.length}/2000</p>
                </Field>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <TagBar tags={["API", "HTTP", "Backend"]} />
                  <div className="flex gap-2">
                    <button className="secondary-button">Cancel</button>
                    <button onClick={() => void ingestText()} className="primary-button">
                      Store to Memory
                    </button>
                  </div>
                </div>
              </div>
            </Panel>
          </section>
          <section className="space-y-4">
            <Panel title="Upload a PDF">
              <label className="flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-cyan-300/35 bg-cyan-300/5 p-6 text-center">
                <CloudUpload className="mb-4 h-10 w-10 text-[#14f1c8]" />
                <span className="font-semibold">Drag and drop your PDF here</span>
                <span className="mt-2 text-sm text-cyan-100/55">Max file size 50MB</span>
                <input
                  type="file"
                  accept=".pdf,.txt,.md,.docx"
                  className="sr-only"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                />
              </label>
              {selectedFile && (
                <div className="mt-3 flex items-center justify-between rounded-md border border-cyan-300/15 bg-[#081d31] px-3 py-3 text-sm">
                  <span>{selectedFile.name}</span>
                  <button onClick={() => setSelectedFile(null)} aria-label="Remove file">
                    <X className="h-4 w-4 text-cyan-100/70" />
                  </button>
                </div>
              )}
              <button onClick={() => void uploadDocument()} className="primary-button mt-4 w-full justify-center">
                Process PDF
              </button>
            </Panel>
            <Panel title="Add URL">
              <Field label="URL">
                <input
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  className="input"
                  placeholder="https://example.com/article"
                />
              </Field>
              <button onClick={() => void ingestUrl()} className="primary-button mt-4 w-full justify-center">
                Save URL
              </button>
            </Panel>
            {processingOpen && <ProcessingFlow fileName={selectedFile?.name ?? "machine-learning.pdf"} />}
          </section>
        </div>
      );
    }

    if (activeView === "Search") {
      return (
        <div className="space-y-5">
          <SectionHeading title="Search Your Memory" subtitle="Find anything you have learned." />
          <div className="panel p-4">
            <div className="flex flex-col gap-3 md:flex-row">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void runSearch()}
                className="input flex-1"
                placeholder="Search for concepts, documents, notes..."
              />
              <button onClick={() => void runSearch()} className="primary-button justify-center">
                <Search className="h-4 w-4" />
                Search
              </button>
            </div>
            <TagBar tags={["All", "Documents", "Notes", "Code", "Videos", "Concepts", "Topics"]} large />
          </div>
          <SearchResults />
        </div>
      );
    }

    if (activeView === "Ask My Memory") {
      return (
        <div className="grid gap-5 xl:grid-cols-[0.8fr_1.1fr]">
          <Panel title="Ask My Memory">
            <div className="mb-4 flex justify-end">
              <div className="grid h-16 w-16 place-items-center rounded-md border border-cyan-300/20 bg-cyan-300/10">
                <Brain className="h-9 w-9 text-[#14f1c8]" />
              </div>
            </div>
            <textarea
              value={chatQuestion}
              onChange={(event) => setChatQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendChat();
                }
              }}
              className="input min-h-48 resize-none"
              placeholder="What did I learn about APIs last month?"
            />
            <div className="mt-3 flex justify-end">
              <button onClick={() => void sendChat()} disabled={chatLoading} className="primary-button">
                {chatLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}
                Ask My Memory
              </button>
            </div>
            <div className="mt-5 space-y-2">
              {["What did I learn about Python?", "Explain FastAPI using what I already know.", "How are Python and APIs connected?"].map(
                (item) => (
                  <button
                    key={item}
                    onClick={() => setChatQuestion(item)}
                    className="w-full rounded-md border border-cyan-300/15 bg-[#07192a] px-3 py-2 text-left text-sm text-cyan-100/80"
                  >
                    {item}
                  </button>
                )
              )}
            </div>
          </Panel>
          <ConversationPanel />
        </div>
      );
    }

    if (activeView === "Knowledge Graph") {
      return (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SectionHeading title="Knowledge Graph" subtitle="Visualize how your knowledge is connected." />
            <div className="flex gap-2">
              <input
                value={graphQuery}
                onChange={(event) => setGraphQuery(event.target.value)}
                className="input w-64"
                placeholder="Graph search..."
              />
              <button onClick={() => void loadGraph()} className="secondary-button">
                Load
              </button>
            </div>
          </div>
          <TagBar tags={["All", "Concepts", "Topics", "Technologies", "Documents"]} large />
          <div className="grid gap-4 xl:grid-cols-[1fr_330px]">
            <div className="panel h-[620px] overflow-hidden">
              <ReactFlow
                nodes={graphNodes}
                edges={graphEdges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={(_, node) => setSelectedNode(node)}
                fitView
              >
                <Background color="#155e75" gap={24} />
                <Controls />
              </ReactFlow>
            </div>
            <GraphDetails />
          </div>
        </div>
      );
    }

    if (activeView === "Timeline") {
      return (
        <Panel title="Memory Timeline" action="Last 30 days">
          <div className="space-y-4">
            {sampleTimeline.map(([date, action, title], index) => (
              <div key={`${date}-${title}`} className="grid gap-3 md:grid-cols-[130px_1fr]">
                <p className="text-sm text-cyan-100/55">{date}</p>
                <div className="flex items-center gap-3 rounded-md border border-cyan-300/15 bg-[#081d31] p-3">
                  <div className="grid h-8 w-8 place-items-center rounded-md bg-[#14f1c8]/15 text-[#14f1c8]">
                    {index % 2 ? <Upload className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{action}</p>
                    <p className="text-xs text-cyan-100/55">{title}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      );
    }

    if (activeView === "Settings") {
      return (
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <Panel title="Settings">
            <div className="space-y-2">
              {["Profile", "Account", "Security", "AI Preferences"].map((item, index) => (
                <button
                  key={item}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                    index === 0 ? "bg-[#14f1c8]/15 text-[#14f1c8]" : "text-cyan-100/70 hover:bg-white/5"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Profile Information">
            <div className="grid max-w-xl gap-4">
              <div className="flex items-center gap-4">
                <div className="grid h-16 w-16 place-items-center rounded-full bg-blue-500/25 text-xl font-bold">A</div>
                <button className="text-sm text-[#14f1c8]">Change photo</button>
              </div>
              <Field label="Name">
                <input className="input" value={displayName} readOnly />
              </Field>
              <Field label="Email">
                <input className="input" value={userEmail} readOnly />
              </Field>
              <button className="primary-button w-fit">Save Changes</button>
            </div>
          </Panel>
        </div>
      );
    }

    if (activeView === "Conversations") {
      return (
        <div className="grid gap-4 xl:grid-cols-[330px_1fr]">
          <Panel title="Conversations">
            {["API learning", "Python notes", "Machine learning", "Java concepts"].map((item, index) => (
              <button key={item} className="mb-2 w-full rounded-md border border-cyan-300/15 bg-[#081d31] p-3 text-left">
                <p className="text-sm font-medium">{item}</p>
                <p className="text-xs text-cyan-100/45">{index + 1} messages</p>
              </button>
            ))}
          </Panel>
          <ConversationPanel />
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <SectionHeading title="Memories" subtitle="All saved notes, documents, and sources." />
        {selectedDocument && (
          <Panel title={selectedDocument.title}>
            <p className="mb-3 text-sm text-cyan-100/60">{selectedDocument.processing_status}</p>
            <div className="space-y-2">
              {selectedDocument.chunks?.map((chunk) => (
                <p key={chunk.id} className="rounded-md bg-[#07192a] p-3 text-sm leading-6 text-cyan-100/80">
                  {chunk.content}
                </p>
              ))}
            </div>
          </Panel>
        )}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(documents.length ? documents : mockDocuments()).map((document) => (
            <article key={document.id} className="panel p-4">
              <div className="flex items-start justify-between gap-3">
                <button onClick={() => void openDocument(document.id)} className="text-left font-semibold text-white">
                  {document.title}
                </button>
                <span className="rounded-md border border-[#14f1c8]/30 px-2 py-1 text-xs text-[#14f1c8]">
                  {document.processing_status}
                </span>
              </div>
              <p className="mt-2 text-sm text-cyan-100/55">{document.source_type}</p>
              {document.error_message && <p className="mt-2 text-sm text-red-300">{document.error_message}</p>}
              <div className="mt-4 flex gap-2">
                <button onClick={() => void extractGraph(document.id)} className="secondary-button">
                  Extract Graph
                </button>
                <button onClick={() => void openDocument(document.id)} className="secondary-button">
                  Open
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    );
  }

  function RecentMemories() {
    const items = documents.length ? documents.slice(0, 4) : mockDocuments().slice(0, 3);
    return (
      <div className="space-y-2">
        {items.map((document) => (
          <button
            key={document.id}
            onClick={() => void openDocument(document.id)}
            className="flex w-full items-center justify-between gap-3 rounded-md border border-cyan-300/15 bg-[#081d31] p-3 text-left"
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-white">{document.title}</span>
              <span className="text-xs text-cyan-100/45">{document.source_type}</span>
            </span>
            <span className="rounded-md border border-[#14f1c8]/30 px-2 py-1 text-xs text-[#14f1c8]">Completed</span>
          </button>
        ))}
      </div>
    );
  }

  function SearchResults() {
    const items = results.length ? results : mockSearchResults();
    return (
      <div className="space-y-3">
        {items.map((result) => (
          <button
            key={result.chunk_id}
            onClick={() => void openDocument(result.document_id)}
            className="panel block w-full p-4 text-left"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold text-white">{result.title}</p>
              <span className="rounded-md bg-[#14f1c8]/12 px-2 py-1 text-xs text-[#14f1c8]">
                {Math.round((result.score || 0.88) * 100)}% relevance
              </span>
            </div>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-cyan-100/65">{result.content}</p>
          </button>
        ))}
      </div>
    );
  }

  function ConversationPanel() {
    return (
      <Panel
        title="AI Answer + Sources"
        action={
          <button
            onClick={() => {
              setConversationId(null);
              setChatTurns([]);
            }}
            className="secondary-button py-1 text-xs"
          >
            New Chat
          </button>
        }
      >
        <div className="flex min-h-[520px] flex-col">
          <div className="flex-1 space-y-3 overflow-auto pr-1">
            {(chatTurns.length ? chatTurns : mockConversation()).map((turn, index) => (
              <div
                key={`${turn.role}-${index}`}
                className={`max-w-[86%] rounded-md border p-4 ${
                  turn.role === "user"
                    ? "ml-auto border-cyan-300/20 bg-cyan-300/10"
                    : "border-[#14f1c8]/20 bg-[#0a2035]"
                }`}
              >
                <p className="mb-2 text-xs font-semibold uppercase text-cyan-100/45">
                  {turn.role === "user" ? "You" : turn.grounded === false ? "AI Memory no source" : "AI Memory"}
                </p>
                <p className="whitespace-pre-wrap text-sm leading-6 text-cyan-50/90">{turn.content}</p>
                {turn.citations && turn.citations.length > 0 && (
                  <div className="mt-4 space-y-2 border-t border-cyan-300/10 pt-3">
                    <p className="text-xs font-semibold text-cyan-100/55">Sources</p>
                    {turn.citations.map((citation) => (
                      <button
                        key={citation.chunk_id}
                        onClick={() => void openDocument(citation.document_id)}
                        className="block w-full rounded-md bg-[#07192a] px-3 py-2 text-left text-xs text-cyan-100/70"
                      >
                        [{citation.citation_id}] {citation.title}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2 border-t border-cyan-300/10 pt-4">
            <input
              value={chatQuestion}
              onChange={(event) => setChatQuestion(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void sendChat()}
              className="input flex-1"
              placeholder="Ask a follow-up question..."
            />
            <button onClick={() => void sendChat()} className="primary-button px-3" aria-label="Send question">
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </Panel>
    );
  }

  function GraphDetails() {
    return (
      <Panel title="Graph Node Details">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-xl font-semibold">{selectedNode ? String(selectedNode.data.label) : "Python"}</h3>
            <span className="mt-1 inline-flex rounded-md bg-blue-500/20 px-2 py-1 text-xs text-blue-200">Concept</span>
          </div>
          <button onClick={() => setSelectedNode(null)} aria-label="Clear selected node">
            <X className="h-4 w-4 text-cyan-100/55" />
          </button>
        </div>
        <div className="space-y-4 text-sm">
          <div>
            <p className="mb-2 text-cyan-100/45">Referenced in documents</p>
            <ul className="space-y-1 text-cyan-50/85">
              <li>FastAPI</li>
              <li>NumPy</li>
              <li>Machine Learning</li>
              <li>Data Analysis</li>
            </ul>
          </div>
          <div>
            <p className="mb-2 text-cyan-100/45">Relationships</p>
            {(selectedRelationships.length ? selectedRelationships : relationships).slice(0, 4).map((item) => (
              <p key={`${item.source}-${item.target}-${item.type}`} className="mb-1 text-cyan-100/75">
                {item.type}: {item.source} to {item.target}
              </p>
            ))}
            {!relationships.length && (
              <>
                <p className="mb-1 text-cyan-100/75">Used to: FastAPI</p>
                <p className="mb-1 text-cyan-100/75">Related to: Machine Learning</p>
              </>
            )}
          </div>
          <button onClick={() => setActiveView("Memories")} className="primary-button w-full justify-center">
            View related documents
          </button>
        </div>
      </Panel>
    );
  }
}

function AuthWebsite({
  mode,
  setMode,
  email,
  setEmail,
  password,
  setPassword,
  fullName,
  setFullName,
  onSubmit,
  status
}: {
  mode: "login" | "register";
  setMode: (mode: "login" | "register") => void;
  email: string;
  setEmail: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
  fullName: string;
  setFullName: (value: string) => void;
  onSubmit: () => void;
  status: string;
}) {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#07182a] text-slate-100">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_20%,rgba(20,241,200,0.16),transparent_30%),radial-gradient(circle_at_75%_15%,rgba(59,130,246,0.16),transparent_28%),linear-gradient(135deg,#0b2a45,#07111e_48%,#020711)]" />
      <div className="relative mx-auto grid min-h-screen max-w-6xl items-center gap-8 px-5 py-10 lg:grid-cols-[1fr_0.82fr]">
        <section className="panel min-h-[640px] overflow-hidden p-7">
          <Logo />
          <div className="mt-10 max-w-md">
            <h1 className="text-3xl font-semibold text-white">Your Personal Second Brain</h1>
            <p className="mt-4 text-sm leading-6 text-cyan-100/70">
              Turn everything you read, learn, and create into a connected personal knowledge system.
            </p>
          </div>
          <div className="mt-8 space-y-4">
            <Feature icon={FileText} title="Save Knowledge" />
            <Feature icon={Network} title="Build Connections" />
            <Feature icon={Bot} title="Ask Anything" />
          </div>
          <Constellation />
        </section>
        <section className="panel p-7">
          <div className="mb-6 flex gap-2 rounded-md border border-cyan-300/15 bg-[#07192a] p-1">
            <button
              onClick={() => setMode("login")}
              className={`flex-1 rounded-md px-3 py-2 text-sm ${mode === "login" ? "bg-[#14f1c8] text-[#03131f]" : "text-cyan-100/70"}`}
            >
              Login
            </button>
            <button
              onClick={() => setMode("register")}
              className={`flex-1 rounded-md px-3 py-2 text-sm ${mode === "register" ? "bg-[#14f1c8] text-[#03131f]" : "text-cyan-100/70"}`}
            >
              Register
            </button>
          </div>
          <h2 className="text-2xl font-semibold text-white">{mode === "login" ? "Welcome Back" : "Create your account"}</h2>
          <p className="mt-2 text-sm text-cyan-100/55">
            {mode === "login" ? "Sign in to continue to your memory." : "Join AI Memory and start building your second brain."}
          </p>
          <div className="mt-6 space-y-4">
            {mode === "register" && (
              <Field label="Full name">
                <div className="field-shell">
                  <CircleUserRound className="h-4 w-4 text-cyan-100/45" />
                  <input value={fullName} onChange={(event) => setFullName(event.target.value)} className="field-input" />
                </div>
              </Field>
            )}
            <Field label="Email address">
              <div className="field-shell">
                <Mail className="h-4 w-4 text-cyan-100/45" />
                <input value={email} onChange={(event) => setEmail(event.target.value)} className="field-input" />
              </div>
            </Field>
            <Field label="Password">
              <div className="field-shell">
                <KeyRound className="h-4 w-4 text-cyan-100/45" />
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  className="field-input"
                />
                <Lock className="h-4 w-4 text-cyan-100/35" />
              </div>
            </Field>
            {mode === "register" && (
              <Field label="Confirm password">
                <div className="field-shell">
                  <ShieldCheck className="h-4 w-4 text-cyan-100/45" />
                  <input value={password} readOnly type="password" className="field-input" />
                </div>
              </Field>
            )}
            <button onClick={onSubmit} className="primary-button w-full justify-center">
              {mode === "login" ? "Login" : "Create Account"}
            </button>
            <p className="text-center text-sm text-cyan-100/55">
              {mode === "login" ? "Do not have an account?" : "Already have an account?"}{" "}
              <button onClick={() => setMode(mode === "login" ? "register" : "login")} className="font-semibold text-[#14f1c8]">
                {mode === "login" ? "Create account" : "Login"}
              </button>
            </p>
            <p className="rounded-md border border-cyan-300/15 bg-[#07192a] p-3 text-sm text-cyan-100/65">{status}</p>
          </div>
        </section>
      </div>
    </main>
  );
}

function Sidebar({
  activeView,
  setActiveView,
  userName,
  onLogout
}: {
  activeView: View;
  setActiveView: (view: View) => void;
  userName: string;
  onLogout: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <Logo compact />
      <nav className="mt-8 space-y-1">
        {navItems.map(({ label, icon: Icon }) => (
          <button
            key={label}
            onClick={() => setActiveView(label)}
            className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition ${
              activeView === label ? "bg-[#14f1c8]/16 text-[#14f1c8]" : "text-cyan-100/70 hover:bg-white/5"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </button>
        ))}
      </nav>
      <button onClick={onLogout} className="mt-auto flex items-center gap-3 rounded-md border border-cyan-300/15 bg-[#07192a] p-3 text-left">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-blue-500/30 text-sm font-semibold">A</div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{userName}</p>
          <p className="text-xs text-cyan-100/45">Free Plan</p>
        </div>
      </button>
    </div>
  );
}

function Topbar({
  query,
  setQuery,
  onSearch,
  onMenu,
  userName
}: {
  query: string;
  setQuery: (value: string) => void;
  onSearch: () => void;
  onMenu: () => void;
  userName: string;
}) {
  return (
    <header className="sticky top-0 z-10 border-b border-cyan-300/15 bg-[#061321]/85 px-4 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] items-center gap-3">
        <button onClick={onMenu} className="secondary-button px-2 lg:hidden" aria-label="Open navigation">
          <Menu className="h-4 w-4" />
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-cyan-300/15 bg-[#07192a] px-3 py-2">
          <Search className="h-4 w-4 text-cyan-100/45" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onSearch()}
            className="w-full bg-transparent text-sm outline-none placeholder:text-cyan-100/35"
            placeholder="Search your memory..."
          />
        </div>
        <button className="secondary-button px-2" aria-label="Notifications">
          <Bell className="h-4 w-4" />
        </button>
        <div className="grid h-9 w-9 place-items-center rounded-full bg-blue-500/30 text-sm font-semibold">
          {userName.slice(0, 1).toUpperCase()}
        </div>
      </div>
    </header>
  );
}

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-10 w-10 place-items-center rounded-md border border-[#14f1c8]/35 bg-[#14f1c8]/10">
        <Brain className="h-6 w-6 text-[#14f1c8]" />
      </div>
      <div>
        <p className="text-lg font-semibold text-white">AI Memory</p>
        {!compact && <p className="text-xs text-cyan-100/45">Connected knowledge</p>}
      </div>
    </div>
  );
}

function Feature({ icon: Icon, title }: { icon: typeof Brain; title: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-cyan-100/75">
      <div className="grid h-8 w-8 place-items-center rounded-md border border-[#14f1c8]/25 bg-[#14f1c8]/10">
        <Icon className="h-4 w-4 text-[#14f1c8]" />
      </div>
      {title}
    </div>
  );
}

function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-semibold text-white">{title}</h2>
        {typeof action === "string" ? <button className="text-xs text-[#14f1c8]">{action}</button> : action}
      </div>
      {children}
    </section>
  );
}

function SectionHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      <p className="mt-1 text-sm text-cyan-100/60">{subtitle}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-cyan-100/75">{label}</span>
      {children}
    </label>
  );
}

function StatCard({ icon: Icon, label, value, tone = "emerald" }: { icon: typeof Brain; label: string; value: string; tone?: string }) {
  const color = tone === "sky" ? "text-sky-300" : tone === "violet" ? "text-violet-300" : tone === "amber" ? "text-amber-300" : "text-[#14f1c8]";
  return (
    <article className="panel p-4">
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm text-cyan-100/55">{label}</span>
        <Icon className={`h-5 w-5 ${color}`} />
      </div>
      <p className="text-3xl font-semibold text-white">{value}</p>
    </article>
  );
}

function MiniChart() {
  const bars = [18, 20, 19, 24, 32, 22, 26, 27, 30, 55, 47, 72, 86];
  return (
    <div className="h-64">
      <div className="flex h-52 items-end gap-3 border-b border-l border-cyan-300/10 px-3">
        {bars.map((height, index) => (
          <div key={index} className="flex flex-1 flex-col items-center gap-2">
            <div className="w-full rounded-t-md bg-gradient-to-t from-[#0ea5e9]/30 to-[#14f1c8]" style={{ height: `${height}%` }} />
          </div>
        ))}
      </div>
      <div className="mt-3 flex justify-between text-xs text-cyan-100/35">
        <span>Sep 29</span>
        <span>Oct 1</span>
        <span>Oct 4</span>
        <span>Oct 7</span>
        <span>Oct 10</span>
        <span>Oct 15</span>
      </div>
    </div>
  );
}

function TopicList() {
  return (
    <div className="space-y-3">
      {sampleTopics.map(([topic, count]) => (
        <div key={topic} className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-cyan-100/80">
            <span className="h-2 w-2 rounded-full bg-[#14f1c8]" />
            {topic}
          </span>
          <span className="text-sm text-cyan-100/55">{count}</span>
        </div>
      ))}
    </div>
  );
}

function DonutLegend() {
  return (
    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
      <div className="aspect-square rounded-full bg-[conic-gradient(#14f1c8_0_38%,#38bdf8_38%_62%,#8b5cf6_62%_84%,#facc15_84%_100%)] p-5">
        <div className="h-full rounded-full bg-[#07192a]" />
      </div>
      <div className="space-y-2 text-sm">
        {[
          ["Documents", "42%"],
          ["Videos", "25%"],
          ["Code", "15%"],
          ["Websites", "8%"]
        ].map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 text-cyan-100/70">
            <span>{label}</span>
            <span>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChoiceCard({ icon: Icon, title, copy, compact = false }: { icon: typeof Brain; title: string; copy: string; compact?: boolean }) {
  return (
    <article className={`panel p-5 ${compact ? "min-h-28" : "min-h-56"}`}>
      <Icon className="mb-5 h-8 w-8 text-[#14f1c8]" />
      <h3 className="font-semibold text-white">{title}</h3>
      <p className="mt-3 text-sm leading-6 text-cyan-100/60">{copy}</p>
      <ChevronRight className="mt-4 h-5 w-5 text-[#14f1c8]" />
    </article>
  );
}

function ActionRow({ icon: Icon, label, onClick }: { icon: typeof Brain; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex items-center gap-3 rounded-md border border-cyan-300/15 bg-[#081d31] px-3 py-2 text-left text-sm">
      <Icon className="h-4 w-4 text-[#14f1c8]" />
      {label}
    </button>
  );
}

function TagBar({ tags, large = false }: { tags: string[]; large?: boolean }) {
  return (
    <div className={`flex flex-wrap gap-2 ${large ? "mt-4" : ""}`}>
      {tags.map((tag, index) => (
        <button
          key={tag}
          className={`rounded-md border px-3 py-1 text-xs ${
            index === 0 ? "border-[#14f1c8] bg-[#14f1c8] text-[#03131f]" : "border-cyan-300/15 bg-[#07192a] text-cyan-100/70"
          }`}
        >
          {tag}
        </button>
      ))}
    </div>
  );
}

function ProcessingFlow({ fileName }: { fileName: string }) {
  const steps = ["PDF uploaded", "Text extracted", "Creating chunks", "Generating embeddings", "Building graph", "Generating summary", "Complete"];
  return (
    <Panel title="Processing your document">
      <p className="mb-4 text-sm text-cyan-100/55">{fileName}</p>
      <div className="space-y-3">
        {steps.map((step, index) => (
          <div key={step} className="flex items-center gap-3">
            <div className="grid h-7 w-7 place-items-center rounded-full bg-[#14f1c8] text-[#03131f]">
              {index < steps.length - 1 ? <Check className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
            </div>
            <span className="text-sm text-cyan-100/75">{step}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Constellation() {
  return (
    <div className="relative mt-16 h-72 max-w-lg">
      {[
        [8, 58],
        [17, 35],
        [28, 70],
        [38, 44],
        [52, 30],
        [64, 54],
        [76, 38],
        [87, 66],
        [44, 74],
        [58, 82]
      ].map(([left, top], index) => (
        <span
          key={`${left}-${top}`}
          className={`absolute h-2 w-2 rounded-full ${index % 3 === 0 ? "bg-violet-400" : "bg-[#14f1c8]"}`}
          style={{ left: `${left}%`, top: `${top}%` }}
        />
      ))}
      <div className="absolute left-[12%] top-[50%] h-px w-[70%] rotate-[-12deg] bg-cyan-300/20" />
      <div className="absolute left-[23%] top-[42%] h-px w-[52%] rotate-[18deg] bg-cyan-300/20" />
      <div className="absolute left-[36%] top-[68%] h-px w-[44%] rotate-[-28deg] bg-cyan-300/20" />
    </div>
  );
}

function mockDocuments(): DocumentRead[] {
  return [
    { id: "mock-rest", title: "REST API Basics", source_type: "Note", source_url: null, processing_status: "COMPLETED", error_message: null },
    { id: "mock-fastapi", title: "FastAPI Tutorial", source_type: "PDF", source_url: null, processing_status: "COMPLETED", error_message: null },
    { id: "mock-python", title: "Python Data Analysis", source_type: "Document", source_url: null, processing_status: "COMPLETED", error_message: null }
  ];
}

function mockSearchResults(): SearchResult[] {
  return [
    {
      chunk_id: "mock-search-1",
      document_id: "mock-rest",
      title: "REST API Basics",
      content: "REST APIs allow applications to communicate using HTTP methods and structured JSON responses.",
      score: 0.94
    },
    {
      chunk_id: "mock-search-2",
      document_id: "mock-fastapi",
      title: "FastAPI Tutorial",
      content: "FastAPI is a modern Python framework for building APIs with type hints and automatic docs.",
      score: 0.87
    },
    {
      chunk_id: "mock-search-3",
      document_id: "mock-python",
      title: "Python Data Analysis",
      content: "Pandas and NumPy are essential for data analysis in Python and machine learning workflows.",
      score: 0.83
    }
  ];
}

function mockConversation(): ChatTurn[] {
  return [
    { role: "user", content: "What did I learn about APIs last month?" },
    {
      role: "assistant",
      content:
        "Based on your memory, you learned that REST APIs are architectural style patterns for building web services. They use HTTP methods such as GET, POST, PUT, and DELETE to perform operations on resources.",
      citations: [
        {
          citation_id: 1,
          document_id: "mock-rest",
          chunk_id: "mock-source",
          title: "REST API Basics",
          chunk_index: 0,
          source_type: "Note",
          source_url: null,
          quote: "REST APIs allow applications to communicate using HTTP methods.",
          score: 0.91
        }
      ],
      grounded: true
    }
  ];
}

function graphNodeStyle(background: string): CSSProperties {
  return {
    background,
    border: "1px solid rgba(20,241,200,0.6)",
    borderRadius: 8,
    color: "#effffb",
    fontSize: 12,
    fontWeight: 700,
    padding: "8px 12px"
  };
}

function toFlowNodes(nodes: GraphNode[]): Node[] {
  return nodes.map((node, index) => ({
    id: node.id,
    data: { label: node.name },
    position: {
      x: 130 + 180 * (index % 4),
      y: 90 + 125 * Math.floor(index / 4)
    },
    style: graphNodeStyle(node.labels.includes("Entity") ? "#0891b2" : "#2563eb")
  }));
}

function toFlowEdges(relationships: GraphRelationship[]): Edge[] {
  return relationships.map((relationship) => ({
    id: `${relationship.source}-${relationship.type}-${relationship.target}`,
    source: relationship.source,
    target: relationship.target,
    label: relationship.type,
    animated: true,
    style: { stroke: "#14f1c8" }
  }));
}
