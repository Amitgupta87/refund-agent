"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, sendChat, uploadMedia } from "@/lib/api";
import type { ChatResponse, MediaUploadResponse, OrderSummary } from "@/lib/types";
import { LockedBadge, RefundStatusBadge } from "@/components/StatusBadge";
import { PennyAvatar } from "@/components/Mascot";
import { ThinkingDots } from "@/components/ThinkingDots";

type Message =
  | { kind: "system"; text: string }
  | { kind: "user"; text: string; attachments: PendingMedia[] }
  | { kind: "agent"; data: ChatResponse }
  | { kind: "error"; text: string };

interface PendingMedia {
  media: MediaUploadResponse;
  preview: string;
  file: File;
}

const MAX_PHOTO_BYTES = 2 * 1024 * 1024;        // 2 MB
const MAX_VIDEO_BYTES = 100 * 1024 * 1024;      // 100 MB
const MAX_VIDEO_SECONDS = 60;

const ACCEPTED_IMAGE = ["image/jpeg", "image/png", "image/webp"] as const;
const ACCEPTED_VIDEO = ["video/mp4", "video/quicktime", "video/webm"] as const;
const ACCEPT_ATTRIBUTE = [...ACCEPTED_IMAGE, ...ACCEPTED_VIDEO].join(",");

function readVideoDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(video.duration) ? video.duration : null);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    video.src = url;
  });
}

async function validateClientSide(file: File): Promise<string | null> {
  const isImage = (ACCEPTED_IMAGE as readonly string[]).includes(file.type);
  const isVideo = (ACCEPTED_VIDEO as readonly string[]).includes(file.type);
  if (!isImage && !isVideo) {
    return "Unsupported file type. Allowed: JPEG / PNG / WebP photos, or MP4 / MOV / WebM video.";
  }
  if (isImage && file.size > MAX_PHOTO_BYTES) {
    return "Photo is too large (max 2 MB).";
  }
  if (isVideo && file.size > MAX_VIDEO_BYTES) {
    return "Video is too large (max 100 MB).";
  }
  if (isVideo) {
    const duration = await readVideoDuration(file);
    if (duration !== null && duration > MAX_VIDEO_SECONDS) {
      return `Video is too long (max ${MAX_VIDEO_SECONDS}s).`;
    }
  }
  return null;
}

export function ChatPanel({
  token,
  order,
  onDecision,
}: {
  token: string;
  order: OrderSummary;
  onDecision: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<PendingMedia[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([
      {
        kind: "system",
        text: order.admin_locked
          ? `This order is locked by an admin — Penny can't make changes here.`
          : `How can I help with your "${order.product_name}" order (${order.order_id})?`,
      },
    ]);
    setConversationId(null);
    setInput("");
    setPending((cur) => {
      cur.forEach((p) => URL.revokeObjectURL(p.preview));
      return [];
    });
  }, [order.order_id, order.product_name, order.admin_locked]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, loading]);

  async function handleFiles(files: FileList | null) {
    if (!files || !files.length || uploading) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const error = await validateClientSide(file);
        if (error) {
          setMessages((prev) => [...prev, { kind: "error", text: error }]);
          continue;
        }
        try {
          const media = await uploadMedia(token, file);
          const preview = URL.createObjectURL(file);
          setPending((cur) => [...cur, { media, preview, file }]);
        } catch (err) {
          const msg =
            err instanceof ApiError ? err.message : "Upload failed.";
          setMessages((prev) => [...prev, { kind: "error", text: msg }]);
        }
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function removePending(media_id: string) {
    setPending((cur) => {
      const next = cur.filter((p) => p.media.media_id !== media_id);
      const removed = cur.find((p) => p.media.media_id === media_id);
      if (removed) URL.revokeObjectURL(removed.preview);
      return next;
    });
  }

  async function submit(text: string) {
    const msg = text.trim();
    if ((!msg && pending.length === 0) || loading) return;
    const attachments = pending;
    setMessages((prev) => [
      ...prev,
      { kind: "user", text: msg || "(attached media)", attachments },
    ]);
    setInput("");
    setPending([]);
    setLoading(true);
    try {
      const data = await sendChat(token, {
        order_id: order.order_id,
        message: msg || "(media attached)",
        conversation_id: conversationId,
        media_ids: attachments.map((a) => a.media.media_id),
      });
      setConversationId(data.conversation_id);
      setMessages((prev) => [...prev, { kind: "agent", data }]);
      if (data.decision !== "none") onDecision();
    } catch (err) {
      const text =
        err instanceof ApiError
          ? err.status === 503
            ? "The assistant is temporarily unavailable. Please try again shortly."
            : `Error: ${err.message}`
          : "Could not reach the assistant. Please try again.";
      setMessages((prev) => [...prev, { kind: "error", text }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-[70vh] flex-col overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/70">
      <div className="flex items-center gap-3 border-b border-slate-200 bg-gradient-to-r from-sky-50 to-white px-4 py-3">
        <PennyAvatar size={40} online priority />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <span>Penny</span>
            <span className="font-normal text-slate-400">· Customer Support</span>
            {order.admin_locked && <LockedBadge />}
          </div>
          <div className="truncate text-xs text-slate-400">
            {order.product_name} · {order.order_id} · ${order.order_amount.toFixed(2)} ·{" "}
            {order.order_status}
          </div>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((m, i) => {
          if (m.kind === "system") {
            return (
              <p key={i} className="animate-fade-in text-center text-xs text-slate-400">
                {m.text}
              </p>
            );
          }
          if (m.kind === "user") {
            return (
              <div key={i} className="flex animate-fade-up">
                <div className="ml-auto flex max-w-[85%] flex-col items-end gap-1">
                  {m.attachments.length > 0 && (
                    <div className="flex flex-wrap justify-end gap-1">
                      {m.attachments.map((a) => (
                        <AttachmentChip key={a.media.media_id} pending={a} />
                      ))}
                    </div>
                  )}
                  <div className="rounded-2xl rounded-tr-sm bg-gradient-to-br from-sky-500 to-blue-600 px-4 py-2 text-sm text-white shadow-sm">
                    {m.text}
                  </div>
                </div>
              </div>
            );
          }
          if (m.kind === "error") {
            return (
              <div
                key={i}
                className="animate-fade-up rounded-md bg-red-50 px-4 py-2 text-sm text-red-700 ring-1 ring-red-200"
              >
                {m.text}
              </div>
            );
          }
          return (
            <div key={i} className="flex animate-fade-up items-end gap-2">
              <PennyAvatar size={28} />
              <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200">
                {m.data.decision !== "none" && (
                  <div className="mb-2">
                    <RefundStatusBadge decision={m.data.decision} />
                  </div>
                )}
                <p className="whitespace-pre-wrap text-sm text-slate-800">
                  {m.data.final_response}
                </p>
              </div>
            </div>
          );
        })}
        {loading && (
          <div className="flex animate-fade-in items-end gap-2">
            <PennyAvatar size={28} />
            <div className="rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200">
              <ThinkingDots />
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-white p-3">
        {pending.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {pending.map((p) => (
              <AttachmentChip
                key={p.media.media_id}
                pending={p}
                onRemove={() => removePending(p.media.media_id)}
              />
            ))}
          </div>
        )}

        {messages.length <= 1 && !order.admin_locked && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            <SuggestionButton
              onClick={() => void submit("I'd like to request a refund for this order.")}
            >
              Request a refund
            </SuggestionButton>
            <SuggestionButton
              onClick={() => void submit("I'd like a replacement for this order.")}
            >
              Request a replacement
            </SuggestionButton>
            <SuggestionButton
              onClick={() => void submit("The item arrived damaged.")}
            >
              Arrived damaged
            </SuggestionButton>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit(input);
          }}
          className="flex items-center gap-2"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_ATTRIBUTE}
            multiple
            className="hidden"
            onChange={(e) => void handleFiles(e.target.files)}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading || uploading || order.admin_locked}
            aria-label="Attach photo or video"
            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 transition hover:bg-slate-50 active:scale-[0.98] disabled:opacity-50"
          >
            <svg viewBox="0 0 20 20" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M8.5 14.5a4 4 0 0 1-2.83-6.83l5.66-5.66a2.5 2.5 0 0 1 3.54 3.54l-5.66 5.66a1 1 0 0 1-1.42-1.42l5.66-5.66a.5.5 0 1 1 .71.71L8.5 10.5a2 2 0 1 0 2.83 2.83l5.66-5.66a3.5 3.5 0 0 0-4.95-4.95L6.38 8.38a5 5 0 0 0 7.07 7.07l5.66-5.66a.5.5 0 1 1 .71.71l-5.66 5.66a6 6 0 0 1-5.66 1Z"/>
            </svg>
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              order.admin_locked
                ? "This order is locked by an admin"
                : "Type your message…"
            }
            aria-label="Your message to Penny"
            disabled={order.admin_locked}
            className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-200 disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={
              loading ||
              uploading ||
              order.admin_locked ||
              (!input.trim() && pending.length === 0)
            }
            className="btn-primary"
          >
            {uploading ? "Uploading…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}

function SuggestionButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 transition hover:bg-sky-100 active:scale-[0.98]"
    >
      {children}
    </button>
  );
}

function AttachmentChip({
  pending,
  onRemove,
}: {
  pending: PendingMedia;
  onRemove?: () => void;
}) {
  const isImage = pending.media.kind === "image";
  return (
    <div className="relative inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white p-1 pr-2 text-xs">
      {isImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={pending.preview}
          alt=""
          width={28}
          height={28}
          className="h-7 w-7 rounded object-cover"
        />
      ) : (
        <span className="grid h-7 w-7 place-items-center rounded bg-slate-100 text-[10px] font-medium text-slate-500">
          VID
        </span>
      )}
      <span className="max-w-[8rem] truncate text-slate-700">{pending.file.name}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove attachment"
          className="ml-1 text-slate-400 hover:text-slate-600"
        >
          ×
        </button>
      )}
    </div>
  );
}
