// 아직 콘텐츠가 없는 화면의 자리. 셸이 동작하는지 눈으로 확인하는 용도이기도 하다.
export function Placeholder({ note }: { note: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
      {note}
    </div>
  )
}
