import { ImagePlus, Link2, Plus, Trash2, UploadCloud } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from "react";

import { CharacterImage } from "@/components/room/CharacterImage";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { MAX_CHARACTER_IMAGE_BYTES } from "@/config";
import { newRequestId } from "@/lib/ids";
import { useRoomStore } from "@/stores/roomStore";
import {
  CATEGORY_LABELS,
  CHARACTER_CATEGORIES,
  type CharacterCategory,
} from "@/types/api";

type Source = "upload" | "url";

interface AttributeRow {
  id: string;
  key: string;
  value: string;
}

function emptyAttribute(): AttributeRow {
  return { id: newRequestId(), key: "", value: "" };
}

export function AddCharacterDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const addCharacter = useRoomStore((state) => state.addCharacter);
  const [name, setName] = useState("");
  const [franchise, setFranchise] = useState("");
  const [category, setCategory] = useState<CharacterCategory>("anime");
  const [source, setSource] = useState<Source>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [attributes, setAttributes] = useState<AttributeRow[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setFilePreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setFilePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const preview = source === "upload" ? filePreview : imageUrl.trim() || null;

  function reset() {
    setName("");
    setFranchise("");
    setCategory("anime");
    setSource("upload");
    setFile(null);
    setImageUrl("");
    setAttributes([]);
    setError(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function close() {
    if (submitting) {
      return;
    }
    setError(null);
    onClose();
  }

  function acceptFile(candidate: File | null | undefined) {
    if (!candidate) {
      return;
    }
    if (!candidate.type.startsWith("image/")) {
      setError("Choose an image file (PNG, JPEG, WebP, or GIF).");
      return;
    }
    if (candidate.size > MAX_CHARACTER_IMAGE_BYTES) {
      setError("Images must be 5 MB or smaller.");
      return;
    }
    setError(null);
    setFile(candidate);
    setSource("upload");
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0]);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Give the character a name.");
      return;
    }
    if (trimmedName.length > 80) {
      setError("Character names can be at most 80 characters.");
      return;
    }
    if (source === "upload" && !file) {
      setError("Choose an image file for this character.");
      return;
    }
    if (source === "url") {
      const trimmedUrl = imageUrl.trim();
      if (!/^https?:\/\//i.test(trimmedUrl)) {
        setError("Enter a full http:// or https:// image URL.");
        return;
      }
    }

    const mergedAttributes: Record<string, string> = {};
    for (const row of attributes) {
      const key = row.key.trim();
      if (!key) {
        continue;
      }
      mergedAttributes[key] = row.value.trim();
    }

    const payload = {
      name: trimmedName,
      franchise: franchise.trim() || null,
      category,
      attributes: mergedAttributes,
    };

    setSubmitting(true);
    const added = file
      ? await addCharacter(payload, file)
      : await addCharacter({ ...payload, image_url: imageUrl.trim() });
    setSubmitting(false);

    if (added) {
      reset();
      onClose();
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Add a character"
      description="Characters form the shared pool. Each player is assigned one they cannot see."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="add-character-form" loading={submitting}>
            Add character
          </Button>
        </>
      }
    >
      <form id="add-character-form" onSubmit={onSubmit} noValidate className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="character-name" required>
            <TextInput
              id="character-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Sherlock Holmes"
              maxLength={80}
              autoFocus
            />
          </Field>
          <Field label="Franchise" htmlFor="character-franchise" hint="Optional">
            <TextInput
              id="character-franchise"
              value={franchise}
              onChange={(event) => setFranchise(event.target.value)}
              placeholder="e.g. Detective stories"
              maxLength={80}
            />
          </Field>
        </div>

        <Field label="Category" htmlFor="character-category">
          <Select
            id="character-category"
            value={category}
            onChange={(event) => setCategory(event.target.value as CharacterCategory)}
          >
            {CHARACTER_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {CATEGORY_LABELS[value]}
              </option>
            ))}
          </Select>
        </Field>

        <div>
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-slate-200">Image</p>
            <div className="flex rounded-lg border border-white/10 bg-black/25 p-0.5">
              <button
                type="button"
                onClick={() => setSource("upload")}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  source === "upload"
                    ? "bg-violet-500/20 text-violet-100"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <UploadCloud className="h-3.5 w-3.5" aria-hidden="true" />
                Upload
              </button>
              <button
                type="button"
                onClick={() => setSource("url")}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  source === "url"
                    ? "bg-violet-500/20 text-violet-100"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                URL
              </button>
            </div>
          </div>

          <div className="mt-2 grid gap-3 sm:grid-cols-[11rem_minmax(0,1fr)]">
            <div className="aspect-[4/3] overflow-hidden rounded-xl border border-white/10 bg-black/30">
              <CharacterImage
                name={name.trim() || "Character preview"}
                imageUrl={preview}
                rounded="rounded-none"
                className="h-full w-full"
              />
            </div>

            {source === "upload" ? (
              <label
                htmlFor="character-image"
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-5 text-center transition ${
                  dragging
                    ? "border-violet-400/70 bg-violet-500/10"
                    : "border-white/15 bg-black/20 hover:border-white/25 hover:bg-white/[0.03]"
                }`}
              >
                <ImagePlus className="h-6 w-6 text-slate-500" aria-hidden="true" />
                <span className="text-sm font-medium text-slate-300">
                  {file ? file.name : "Choose or drop an image"}
                </span>
                <span className="text-xs text-slate-500">
                  {file
                    ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                    : "PNG, JPEG, WebP, or GIF · up to 5 MB"}
                </span>
                <input
                  ref={inputRef}
                  id="character-image"
                  type="file"
                  accept="image/*"
                  onChange={onFileChange}
                  className="sr-only"
                />
              </label>
            ) : (
              <div className="space-y-2">
                <Field label="Image URL" htmlFor="character-image-url">
                  <TextInput
                    id="character-image-url"
                    value={imageUrl}
                    onChange={(event) => setImageUrl(event.target.value)}
                    placeholder="https://example.com/character.png"
                    inputMode="url"
                  />
                </Field>
                <p className="text-xs leading-5 text-slate-500">
                  The backend downloads and re-encodes remote images. Private or
                  blocked hosts will be rejected.
                </p>
              </div>
            )}
          </div>
        </div>

        <details className="rounded-xl border border-white/10 bg-black/20 p-3">
          <summary className="cursor-pointer select-none text-sm font-medium text-slate-300">
            Optional attributes
          </summary>
          <p className="mt-1 text-xs text-slate-500">
            Add descriptive facts such as “wears a hat” or “is animated”. They
            appear as clues when players view the collection.
          </p>
          <div className="mt-3 space-y-2">
            {attributes.map((row, index) => (
              <div key={row.id} className="flex items-center gap-2">
                <TextInput
                  aria-label={`Attribute ${index + 1} name`}
                  value={row.key}
                  onChange={(event) =>
                    setAttributes((current) =>
                      current.map((item) =>
                        item.id === row.id ? { ...item, key: event.target.value } : item,
                      ),
                    )
                  }
                  placeholder="Attribute"
                  maxLength={40}
                  className="h-9 text-xs"
                />
                <TextInput
                  aria-label={`Attribute ${index + 1} value`}
                  value={row.value}
                  onChange={(event) =>
                    setAttributes((current) =>
                      current.map((item) =>
                        item.id === row.id ? { ...item, value: event.target.value } : item,
                      ),
                    )
                  }
                  placeholder="Value"
                  maxLength={120}
                  className="h-9 text-xs"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label="Remove attribute"
                  className="h-9 w-9 shrink-0 px-0 text-slate-500 hover:text-rose-300"
                  onClick={() =>
                    setAttributes((current) => current.filter((item) => item.id !== row.id))
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setAttributes((current) => [...current, emptyAttribute()])}
              icon={<Plus className="h-3.5 w-3.5" />}
            >
              Add attribute
            </Button>
          </div>
        </details>

        {error ? (
          <p
            className="rounded-xl border border-rose-400/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
            role="alert"
          >
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
