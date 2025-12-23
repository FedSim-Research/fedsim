import { Injectable, WritableSignal, signal } from '@angular/core';
import { Node, Edge } from 'ngx-vflow';

@Injectable({
  providedIn: 'root',
})
export abstract class GraphService {
  public nodes: WritableSignal<Node[]> = signal([]);
  public edges: WritableSignal<Edge[]> = signal([]);

  public addNode(newNode: Node) {
    this.nodes.update((nodes) => [...nodes, newNode]);
  }

  public addEdge(newEdge: Edge) {
    this.edges.update((edges) => [...edges, newEdge]);
  }

  public removeNode(nodeId: String){
    this.nodes.update(nodes => nodes.filter(node => node.id !== nodeId))

    this.edges.update(edges => edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId));
  }

  public removeEdge(edgeToRemove: Edge){
    this.edges.update(edges => edges.filter(edge => edge !== edgeToRemove));
  }

  public resetGraph(){
    this.nodes = signal([]);
    this.edges = signal([]);
  }
}