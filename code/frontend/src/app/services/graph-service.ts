import { Injectable, WritableSignal, signal, inject } from '@angular/core';
import { Node, Edge, NodePositionChange } from 'ngx-vflow';
import { GraphHistoryService } from './graph-history-service';

@Injectable({
  providedIn: 'root',
})
export abstract class GraphService<T extends GraphHistoryService> {
  public nodes: WritableSignal<Node[]> = signal([]);
  public edges: WritableSignal<Edge[]> = signal([]);

  protected constructor(protected graphHistory: T){}

  public addNode(newNode: Node) {
    this.nodes.update((nodes) => [...nodes, newNode]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public addEdge(newEdge: Edge) {
    this.edges.update((edges) => [...edges, newEdge]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeNodeById(nodeId: String){
    this.nodes.update(nodes => nodes.filter(node => node.id !== nodeId));
    this.edges.update(edges => edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeEdge(edgeToRemove: Edge){
    this.edges.update(edges => edges.filter(edge => edge !== edgeToRemove));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeEdgeById(edgeId: String){
    this.edges.update(edges => edges.filter(edge => edge.id !== edgeId));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public resetGraph(){
    this.nodes.set([]);
    this.edges.set([]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public getGraphHistory(){
    return this.graphHistory
  }

  public updateNodePositions(posChanges: NodePositionChange[]){
    const changeMap = new Map(posChanges.map(c => [c.id, c.point]));
    const newNodes = this.nodes().map(node => {
    if (changeMap.has(node.id)) {
      return { 
        ...node, 
        point: changeMap.get(node.id)! 
      };
    }
    return node;
  });
  this.nodes.set(newNodes);
  }
}