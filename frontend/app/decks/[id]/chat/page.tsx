import { redirect } from "next/navigation";

export default function ChatPage({ params }: { params: { id: string } }) {
  redirect(`/decks/${params.id}`);
}
