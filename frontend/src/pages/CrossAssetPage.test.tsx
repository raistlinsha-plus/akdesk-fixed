// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {CrossAssetPage} from "./CrossAssetPage";
import {apiGet} from "../api";
import {syntheticQuotes} from "../crossAssets";
vi.mock("../api",()=>({apiGet:vi.fn()}));
vi.mock("../components/UI",()=>({Panel:({children,title}:{children:React.ReactNode;title:string})=><section><h2>{title}</h2>{children}</section>,WatchButton:()=> <button>加入自选</button>}));
vi.mock("../components/WorkflowCapture",()=>({WorkflowCapture:()=> <button>保存查询引用到项目</button>}));
vi.mock("../components/Charts",()=>({LineChart:()=> <div>日线图</div>}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
it("standalone synthetic journey never requests API and has no research writes",()=>{
  render(<CrossAssetPage synthetic/>);
  expect(screen.getByRole("heading",{name:"股债金汇观察"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"黄金 Au99.99"}));
  expect(screen.getByText(/不是金店零售/)).toBeTruthy();
  expect(screen.queryByRole("button",{name:"保存查询引用到项目"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"整理跨资产观察底稿"}));
  expect(screen.getByRole("button",{name:"下载合成观察底稿"})).toBeTruthy();
  expect(apiGet).not.toHaveBeenCalled();
});
it("loads only quotes initially and history only after explicit request",async()=>{
  vi.mocked(apiGet).mockImplementation(path=>Promise.resolve({data:syntheticQuotes().filter(item=>path.endsWith("kind=gold")?item.kind==="gold":item.kind==="index"),state:"demo",policy:{notice:""}}) as ReturnType<typeof apiGet>);
  render(<CrossAssetPage/>);
  fireEvent.click(await screen.findByRole("button",{name:"上证指数"}));
  expect(apiGet).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button",{name:"按需载入／重读日线"})).toBeTruthy();
  expect(apiGet).not.toHaveBeenCalledWith(expect.stringContaining("/history"),expect.anything());
});
