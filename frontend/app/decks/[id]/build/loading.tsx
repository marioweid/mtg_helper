export default function BuildLoading() {
  return (
    <div className="flex items-center justify-center py-20 gap-3 text-gray-500">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/20 border-t-indigo-500" />
      Generating suggestions...
    </div>
  );
}
